package com.company.cloudctl.dpc

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.UserManager

data class PolicyStatus(
    val deviceOwner: Boolean,
    val adminActive: Boolean,
    val lockTaskPackages: List<String>,
)

data class ManagedInstallRequest(
    val packageName: String,
    val apkUri: Uri,
    val requiresUserConfirmation: Boolean = true,
)

class PolicyController(context: Context) {
    private val appContext = context.applicationContext
    private val manager = appContext.getSystemService(DevicePolicyManager::class.java)
    private val admin = ComponentName(appContext, CloudCtlDeviceAdminReceiver::class.java)

    fun status(): PolicyStatus = PolicyStatus(
        deviceOwner = manager.isDeviceOwnerApp(appContext.packageName),
        adminActive = manager.isAdminActive(admin),
        lockTaskPackages = if (manager.isDeviceOwnerApp(appContext.packageName)) {
            manager.getLockTaskPackages(admin).toList()
        } else {
            emptyList()
        },
    )

    fun applyDedicatedDevicePolicy(packages: List<String>) {
        requireDeviceOwner()
        require(packages.contains(COMPANION_PACKAGE)) {
            "Dedicated-device allowlist must retain the visible Companion app"
        }
        manager.setLockTaskPackages(admin, packages.toTypedArray())
        manager.addUserRestriction(admin, UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES)
        manager.addUserRestriction(admin, UserManager.DISALLOW_DEBUGGING_FEATURES)
    }

    fun clearDedicatedDevicePolicy() {
        requireDeviceOwner()
        manager.setLockTaskPackages(admin, emptyArray())
        manager.clearUserRestriction(admin, UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES)
        manager.clearUserRestriction(admin, UserManager.DISALLOW_DEBUGGING_FEATURES)
    }

    fun prepareManagedInstall(packageName: String, apkUri: Uri): ManagedInstallRequest {
        requireDeviceOwner()
        require(PACKAGE_NAME.matches(packageName)) { "Managed package name is invalid" }
        require(apkUri.scheme == "content") { "Managed APK must use an app-scoped content URI" }
        require(manager.getLockTaskPackages(admin).contains(packageName)) {
            "Managed package is not on the dedicated-device allowlist"
        }
        return ManagedInstallRequest(packageName = packageName, apkUri = apkUri)
    }

    fun launchManagedInstall(activity: Activity, request: ManagedInstallRequest) {
        requireDeviceOwner()
        activity.startActivity(
            Intent(Intent.ACTION_INSTALL_PACKAGE, request.apkUri)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                .putExtra(Intent.EXTRA_RETURN_RESULT, true),
        )
    }

    fun activateKiosk(activity: Activity, packageName: String) {
        requireDeviceOwner()
        check(activity.packageName == packageName) {
            "Kiosk activation must be requested by the foreground allowlisted package"
        }
        check(manager.isLockTaskPermitted(packageName)) {
            "Package is not permitted for lock task mode"
        }
        activity.startLockTask()
    }

    private fun requireDeviceOwner() {
        check(manager.isDeviceOwnerApp(appContext.packageName)) {
            "Policy changes require a company-owned device provisioned with this app as device owner"
        }
    }

    companion object {
        const val COMPANION_PACKAGE = "com.company.cloudctl.companion"
        private val PACKAGE_NAME = Regex("^[a-zA-Z][a-zA-Z0-9_]*(\\.[a-zA-Z0-9_]+)+$")
    }
}
