package com.company.cloudctl.companion.network

import java.io.ByteArrayOutputStream
import java.io.BufferedInputStream
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.URI
import java.security.MessageDigest
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.SNIHostName
import javax.net.ssl.SSLParameters
import javax.net.ssl.SSLSocket
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

internal object PinnedHttpsTransport {
    data class Response(val status: Int, val headers: Map<String, String>, val body: ByteArray)

    fun request(
        baseUrl: String,
        path: String,
        pin: String,
        method: String,
        headers: Map<String, String>,
        body: ByteArray?,
        connectTimeoutMs: Int,
        readTimeoutMs: Int,
    ): Pair<Int, String> {
        val response = requestBytes(baseUrl, path, pin, method, headers, body, connectTimeoutMs, readTimeoutMs, 2 * 1024 * 1024L)
        return response.status to response.body.toString(Charsets.UTF_8)
    }

    fun requestBytes(
        baseUrl: String,
        path: String,
        pin: String,
        method: String,
        headers: Map<String, String>,
        body: ByteArray?,
        connectTimeoutMs: Int,
        readTimeoutMs: Int,
        maxBodyBytes: Long,
    ): Response {
        val uri = URI(baseUrl.trimEnd('/') + path)
        require(uri.scheme == "https" && uri.host != null)
        val host = uri.host
        val port = if (uri.port > 0) uri.port else 443
        val socket = pinnedContext(pin).socketFactory.createSocket() as SSLSocket
        try {
            socket.soTimeout = readTimeoutMs
            socket.connect(InetSocketAddress(host, port), connectTimeoutMs)
            socket.sslParameters = SSLParameters().apply {
                serverNames = listOf(SNIHostName(host))
                endpointIdentificationAlgorithm = null
            }
            socket.startHandshake()
            val target = uri.rawPath.ifBlank { "/" } + (uri.rawQuery?.let { "?$it" } ?: "")
            val payload = buildRequest(method, target, host, headers, body)
            socket.outputStream.write(payload)
            socket.outputStream.flush()
            return readResponse(BufferedInputStream(socket.inputStream), maxBodyBytes)
        } finally {
            runCatching { socket.close() }
        }
    }

    fun requestToFile(
        baseUrl: String,
        path: String,
        pin: String,
        method: String,
        headers: Map<String, String>,
        body: ByteArray?,
        connectTimeoutMs: Int,
        readTimeoutMs: Int,
        maxBodyBytes: Long,
        outputFile: File,
    ): Response {
        val uri = URI(baseUrl.trimEnd('/') + path)
        require(uri.scheme == "https" && uri.host != null)
        val host = uri.host
        val port = if (uri.port > 0) uri.port else 443
        val socket = pinnedContext(pin).socketFactory.createSocket() as SSLSocket
        try {
            socket.soTimeout = readTimeoutMs
            socket.connect(InetSocketAddress(host, port), connectTimeoutMs)
            socket.sslParameters = SSLParameters().apply {
                serverNames = listOf(SNIHostName(host))
                endpointIdentificationAlgorithm = null
            }
            socket.startHandshake()
            val target = uri.rawPath.ifBlank { "/" } + (uri.rawQuery?.let { "?$it" } ?: "")
            socket.outputStream.write(buildRequest(method, target, host, headers, body))
            socket.outputStream.flush()
            outputFile.parentFile?.mkdirs()
            FileOutputStream(outputFile).use { output ->
                return readResponseToFile(BufferedInputStream(socket.inputStream), maxBodyBytes, output)
            }
        } finally {
            runCatching { socket.close() }
        }
    }

    private fun buildRequest(
        method: String,
        target: String,
        host: String,
        headers: Map<String, String>,
        body: ByteArray?,
    ): ByteArray {
        val builder = StringBuilder()
        builder.append(method).append(' ').append(target).append(" HTTP/1.1\r\n")
        builder.append("Host: ").append(host).append("\r\n")
        builder.append("Connection: close\r\n")
        headers.forEach { (key, value) ->
            builder.append(key).append(": ").append(value).append("\r\n")
        }
        if (body != null) builder.append("Content-Length: ").append(body.size).append("\r\n")
        builder.append("\r\n")
        val head = builder.toString().toByteArray(Charsets.US_ASCII)
        if (body == null || body.isEmpty()) return head
        return head + body
    }

    private fun readResponse(input: BufferedInputStream, maxBodyBytes: Long): Response {
        val rawHeaders = ByteArrayOutputStream()
        var matched = 0
        while (rawHeaders.size() <= 64 * 1024) {
            val value = input.read()
            if (value < 0) break
            rawHeaders.write(value)
            matched = when {
                matched == 0 && value == '\r'.code -> 1
                matched == 1 && value == '\n'.code -> 2
                matched == 2 && value == '\r'.code -> 3
                matched == 3 && value == '\n'.code -> 4
                else -> if (value == '\r'.code) 1 else 0
            }
            if (matched == 4) break
        }
        require(matched == 4) { "Cloud response was truncated" }
        val headerText = rawHeaders.toByteArray().toString(Charsets.ISO_8859_1)
        val statusLine = headerText.lineSequence().firstOrNull().orEmpty()
        val status = statusLine.split(' ').getOrNull(1)?.toIntOrNull()
            ?: error("Cloud response status is invalid")
        val headerLines = headerText.substringAfter("\r\n", "").lineSequence()
        val headers = headerLines.mapNotNull { line ->
            line.indexOf(':').takeIf { it > 0 }?.let { index ->
                line.substring(0, index).trim().lowercase() to line.substring(index + 1).trim()
            }
        }.toMap()
        val decoded = if (headers["transfer-encoding"].equals("chunked", ignoreCase = true)) {
            decodeChunked(input, maxBodyBytes)
        } else if (headers["content-length"]?.toLongOrNull()?.also { require(it >= 0) } != null) {
            readFixed(input, headers.getValue("content-length").toLong(), maxBodyBytes)
        } else {
            readUntilEof(input, maxBodyBytes)
        }
        return Response(status, headers, decoded)
    }

    private fun readResponseToFile(input: BufferedInputStream, maxBodyBytes: Long, output: FileOutputStream): Response {
        val rawHeaders = ByteArrayOutputStream()
        var matched = 0
        while (rawHeaders.size() <= 64 * 1024) {
            val value = input.read()
            if (value < 0) break
            rawHeaders.write(value)
            matched = when {
                matched == 0 && value == '\r'.code -> 1
                matched == 1 && value == '\n'.code -> 2
                matched == 2 && value == '\r'.code -> 3
                matched == 3 && value == '\n'.code -> 4
                else -> if (value == '\r'.code) 1 else 0
            }
            if (matched == 4) break
        }
        require(matched == 4) { "Cloud response was truncated" }
        val headerText = rawHeaders.toByteArray().toString(Charsets.ISO_8859_1)
        val statusLine = headerText.lineSequence().firstOrNull().orEmpty()
        val status = statusLine.split(' ').getOrNull(1)?.toIntOrNull()
            ?: error("Cloud response status is invalid")
        val headers = headerText.substringAfter("\r\n", "").lineSequence().mapNotNull { line ->
            line.indexOf(':').takeIf { it > 0 }?.let { index ->
                line.substring(0, index).trim().lowercase() to line.substring(index + 1).trim()
            }
        }.toMap()
        when {
            headers["transfer-encoding"].equals("chunked", ignoreCase = true) -> copyChunkedToFile(input, output, maxBodyBytes)
            headers["content-length"]?.toLongOrNull()?.also { require(it >= 0) } != null ->
                copyFixedToFile(input, output, headers.getValue("content-length").toLong(), maxBodyBytes)
            else -> copyUntilEofToFile(input, output, maxBodyBytes)
        }
        return Response(status, headers, ByteArray(0))
    }

    private fun readFixed(input: BufferedInputStream, length: Long, maxBodyBytes: Long): ByteArray {
        require(length <= maxBodyBytes) { "Cloud response exceeds limit" }
        val output = ByteArrayOutputStream()
        copyLimited(input, output, length, maxBodyBytes)
        return output.toByteArray()
    }

    private fun readUntilEof(input: BufferedInputStream, maxBodyBytes: Long): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            require(output.size().toLong() + count <= maxBodyBytes) { "Cloud response exceeds limit" }
            output.write(buffer, 0, count)
        }
        return output.toByteArray()
    }

    private fun copyLimited(input: BufferedInputStream, output: ByteArrayOutputStream, length: Long, maxBodyBytes: Long) {
        var remaining = length
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        while (remaining > 0) {
            val count = input.read(buffer, 0, minOf(buffer.size.toLong(), remaining).toInt())
            require(count > 0) { "Cloud response was truncated" }
            output.write(buffer, 0, count)
            remaining -= count
            require(output.size().toLong() <= maxBodyBytes) { "Cloud response exceeds limit" }
        }
    }

    private fun copyLimited(
        input: BufferedInputStream,
        output: OutputStream,
        length: Long,
        maxBodyBytes: Long,
        stopAtEof: Boolean = false,
    ) {
        var remaining = length
        var total = 0L
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        while (remaining > 0) {
            val count = input.read(buffer, 0, minOf(buffer.size.toLong(), remaining).toInt())
            if (count < 0 && stopAtEof) break
            require(count > 0) { "Cloud response was truncated" }
            output.write(buffer, 0, count)
            remaining -= count
            total += count
            require(total <= maxBodyBytes) { "Cloud response exceeds limit" }
        }
        if (!stopAtEof) require(remaining == 0L) { "Cloud response was truncated" }
    }

    private fun decodeChunked(input: BufferedInputStream, maxBodyBytes: Long): ByteArray {
        val output = ByteArrayOutputStream()
        while (true) {
            val sizeText = readAsciiLine(input).trim()
            val size = sizeText.substringBefore(';').toInt(16)
            if (size == 0) break
            require(output.size().toLong() + size <= maxBodyBytes) { "Cloud response exceeds limit" }
            copyLimited(input, output, size.toLong(), maxBodyBytes)
            require(input.read() == '\r'.code && input.read() == '\n'.code) { "Invalid chunk terminator" }
        }
        return output.toByteArray()
    }

    private fun copyFixedToFile(input: BufferedInputStream, output: FileOutputStream, length: Long, maxBodyBytes: Long) {
        require(length <= maxBodyBytes) { "Cloud response exceeds limit" }
        copyLimited(input, output, length, maxBodyBytes)
    }

    private fun copyUntilEofToFile(input: BufferedInputStream, output: FileOutputStream, maxBodyBytes: Long) {
        copyLimited(input, output, Long.MAX_VALUE, maxBodyBytes, stopAtEof = true)
    }

    private fun copyChunkedToFile(input: BufferedInputStream, output: FileOutputStream, maxBodyBytes: Long) {
        var total = 0L
        while (true) {
            val sizeText = readAsciiLine(input).trim()
            val size = sizeText.substringBefore(';').toLong(16)
            if (size == 0L) break
            require(total + size <= maxBodyBytes) { "Cloud response exceeds limit" }
            copyLimited(input, output, size, maxBodyBytes)
            total += size
            require(input.read() == '\r'.code && input.read() == '\n'.code) { "Invalid chunk terminator" }
        }
    }

    private fun readAsciiLine(input: BufferedInputStream): String {
        val output = ByteArrayOutputStream()
        while (true) {
            val value = input.read()
            require(value >= 0) { "Cloud response was truncated" }
            if (value == '\n'.code) return output.toByteArray().toString(Charsets.US_ASCII).trimEnd('\r')
            output.write(value)
            require(output.size() <= 8 * 1024) { "Cloud response line exceeds limit" }
        }
    }

    /** p10-live/20260913.1: pinned factory for the live WebSocket client. */
    fun pinnedSocketFactory(pin: String): SSLSocketFactory = pinnedContext(pin).socketFactory

    @Suppress("CustomX509TrustManager")
    private fun pinnedContext(pin: String) = SSLContext.getInstance("TLS").apply {
        val expected = pin.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        val trustManager = object : X509TrustManager {
            override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = error("Not a TLS server")
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                require(chain.isNotEmpty())
                val actual = MessageDigest.getInstance("SHA-256").digest(chain.first().encoded)
                check(MessageDigest.isEqual(actual, expected)) { "Cloud certificate fingerprint mismatch" }
            }
        }
        init(null, arrayOf<TrustManager>(trustManager), null)
    }
}

/** Public pinned trust manager for WS clients (p10-live/20260913.1). */
@Suppress("CustomX509TrustManager")
class PinnedTrustManager(private val pin: String) : X509TrustManager {
    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit
    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
        require(chain.isNotEmpty())
        val expected = pin.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        val actual = MessageDigest.getInstance("SHA-256").digest(chain.first().encoded)
        check(MessageDigest.isEqual(actual, expected)) { "Cloud certificate fingerprint mismatch" }
    }
}
