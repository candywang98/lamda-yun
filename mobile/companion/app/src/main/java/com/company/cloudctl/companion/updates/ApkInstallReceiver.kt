package com.company.cloudctl.companion.updates

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.content.pm.PackageInstaller
import android.os.Build
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest
import java.time.Instant

/**
 * U11: PackageInstaller status receiver (PENDING_USER_ACTION / failure /
 * success) plus the thin Android bridges for the coordinator's injected ports.
 * All state-machine logic lives in [ApkUpdateCoordinator]; this file only
 * translates framework types.
 *
 * The receiver is the statusReceiver target handed to
 * `PackageInstaller.Session.commit(...)`. Deliveries may arrive while no
 * coordinator is attached (the user-confirmation activity can restart the
 * process), so they are journaled into the same on-disk ledger the
 * coordinator drains on [ApkUpdateCoordinator.recoverAfterRestart] — a
 * pending install intent stays resolvable across reboots and is never
 * mistaken for success.
 */
class ApkInstallReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_INSTALL_STATUS) return
        val sessionId = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1)
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
        val outcome = when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_SUCCESS -> ApkInstallerOutcome.SUCCESS
            PackageInstaller.STATUS_PENDING_USER_ACTION -> ApkInstallerOutcome.PENDING_USER_ACTION
            PackageInstaller.STATUS_FAILURE_ABORTED -> ApkInstallerOutcome.FAILURE_ABORTED
            PackageInstaller.STATUS_FAILURE_STORAGE -> ApkInstallerOutcome.FAILURE_STORAGE
            PackageInstaller.STATUS_FAILURE_INCOMPATIBLE -> ApkInstallerOutcome.FAILURE_INCOMPATIBLE
            PackageInstaller.STATUS_FAILURE_BLOCKED -> ApkInstallerOutcome.FAILURE_BLOCKED
            PackageInstaller.STATUS_FAILURE_INVALID -> ApkInstallerOutcome.FAILURE_INVALID
            PackageInstaller.STATUS_FAILURE_CONFLICT -> ApkInstallerOutcome.FAILURE_CONFLICT
            else -> ApkInstallerOutcome.FAILURE
        }
        val sink = ApkInstallStatusBus.current()
        if (sink != null) {
            sink(sessionId, outcome, message)
        } else {
            // Never drop a terminal or pending-user-action delivery: journal it.
            ledger(context).appendStatusEvent(
                ApkInstallerStatusEvent(sessionId, outcome, message, Instant.now().toString()),
            )
        }
    }

    companion object {
        const val ACTION_INSTALL_STATUS = "com.company.cloudctl.companion.updates.ACTION_INSTALL_STATUS"

        /** Shared on-disk home for the ledger + verified artifacts. */
        fun ledgerRoot(context: Context): File = File(context.filesDir, "apk-updates")

        fun ledger(context: Context): FileApkUpdateLedger = FileApkUpdateLedger(ledgerRoot(context))
    }
}

/**
 * Process-wide dispatcher the sync service attaches at startup:
 * `ApkInstallStatusBus.attach { id, outcome, msg -> coordinator.onInstallerStatus(id, outcome, msg) }`.
 */
object ApkInstallStatusBus {
    @Volatile
    private var sink: ((Int, ApkInstallerOutcome, String?) -> Unit)? = null

    fun attach(sink: (Int, ApkInstallerOutcome, String?) -> Unit) {
        this.sink = sink
    }

    fun detach() {
        sink = null
    }

    fun current(): ((Int, ApkInstallerOutcome, String?) -> Unit)? = sink
}

/** [ApkInstallPort] bridge over android.content.pm.PackageInstaller. */
class AndroidPackageInstallerPort(private val context: Context) : ApkInstallPort {

    override fun createSession(): ApkInstallSession {
        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        val id = installer.createSession(params)
        val session = installer.openSession(id)
        return object : ApkInstallSession {
            override val sessionId: Int = id

            override fun stage(file: File) {
                session.openWrite("cloudctl-apk", 0, file.length()).use { output ->
                    FileInputStream(file).use { input -> input.copyTo(output) }
                    session.fsync(output)
                }
            }

            override fun commit() {
                val status = Intent(ApkInstallReceiver.ACTION_INSTALL_STATUS).setPackage(context.packageName)
                val pending = PendingIntent.getBroadcast(
                    context,
                    0,
                    status,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                )
                session.commit(pending.intentSender)
            }

            override fun abandon() {
                session.abandon()
            }

            override fun close() {
                // PackageInstaller.Session.close() abandons an uncommitted session.
                session.close()
            }
        }
    }
}

/** [ApkDeviceStatePort] bridge over PackageManager / Build. */
class AndroidDeviceStatePort(private val context: Context) : ApkDeviceStatePort {

    override val sdkInt: Int
        get() = Build.VERSION.SDK_INT

    override val abis: Set<String>
        get() = Build.SUPPORTED_ABIS.toSet()

    override fun canRequestInstalls(): Boolean = context.packageManager.canRequestPackageInstalls()

    override fun installedVersionCode(packageName: String): Int? = packageInfo(packageName)?.let { info ->
        info.longVersionCode.toInt()
    }

    override fun installedSignatureDigest(packageName: String): String? = try {
        packageInfo(packageName, PackageManager.GET_SIGNING_CERTIFICATES)
            ?.signingInfo
            ?.apkContentsSigners
            ?.firstOrNull()
            ?.let { signature -> sha256Hex(signature.toByteArray()) }
    } catch (_: PackageManager.NameNotFoundException) {
        null
    }

    override fun dataSchemaVersion(packageName: String): Int? = null // surfaced by app data code once U12+ wires it

    private fun packageInfo(packageName: String, flags: Int = 0): PackageInfo? = try {
        context.packageManager.getPackageInfo(packageName, flags)
    } catch (_: PackageManager.NameNotFoundException) {
        null
    }

    private fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
}
