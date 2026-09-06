package com.company.cloudctl.dpc

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent

class CloudCtlDeviceAdminReceiver : DeviceAdminReceiver() {
    override fun onProfileProvisioningComplete(context: Context, intent: Intent) {
        super.onProfileProvisioningComplete(context, intent)
        context.getSharedPreferences(PROVISIONING_STATE, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(PROVISIONING_COMPLETE, true)
            .apply()
        context.startActivity(
            Intent(context, DpcActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
        )
    }

    companion object {
        const val PROVISIONING_STATE = "cloudctl_provisioning"
        const val PROVISIONING_COMPLETE = "profile_provisioning_complete"
    }
}
