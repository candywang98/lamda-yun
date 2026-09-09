package com.company.cloudctl.companion.automation

import org.json.JSONObject
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters
import org.bouncycastle.crypto.signers.Ed25519Signer
import java.util.Base64

object RecipeSignatureVerifier {
    fun verifyPackage(root: JSONObject, publicKeys: Map<String, String>) {
        val signature = root.getJSONObject("signature")
        require(signature.getString("algorithm") == "Ed25519") { CommandV1Parser.UNSUPPORTED_RECIPE }
        val digest = signature.getString("digest")
        require(digest != "hash-pinned-builtin") { "catalog recipe requires an Ed25519 signature" }
        val keyId = signature.getString("keyId")
        val encodedKey = publicKeys[keyId] ?: error("recipe package uses an untrusted signing key")
        val manifest = root.getJSONObject("manifest")
        val hash = manifest.getString("hash")
        val payload = CanonicalJson.dumps(
            JSONObject()
                .put("artifactSha256", hash)
                .put("manifest", JSONObject(manifest.toString()))
                .put("sbomRef", "recipe://local")
                .put("sbomSha256", hash),
        ).toByteArray(Charsets.UTF_8)
        require(verifyEd25519(encodedKey, digest, payload)) { "recipe package signature verification failed" }
    }

    fun verifyEd25519(publicKeyBase64: String, signatureBase64: String, payload: ByteArray): Boolean =
        runCatching {
            val raw = Base64.getDecoder().decode(publicKeyBase64)
            require(raw.size == Ed25519PublicKeyParameters.KEY_SIZE)
            // Android's installed JCA providers do not consistently expose Ed25519.
            // Use the bundled implementation without changing global security providers.
            Ed25519Signer().run {
                init(false, Ed25519PublicKeyParameters(raw, 0))
                update(payload, 0, payload.size)
                verifySignature(Base64.getDecoder().decode(signatureBase64))
            }
        }.getOrDefault(false)
}
