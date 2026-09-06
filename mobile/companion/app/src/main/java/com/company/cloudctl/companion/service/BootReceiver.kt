package com.company.cloudctl.companion.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!ServiceLaunchPolicy.shouldStart(intent.action, CompanionServiceStarter.hasBinding(context))) return
        CompanionServiceStarter.startIfBound(context)
    }
}
