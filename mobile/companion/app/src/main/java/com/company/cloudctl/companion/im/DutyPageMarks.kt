package com.company.cloudctl.companion.im

import android.view.accessibility.AccessibilityNodeInfo

/**
 * Device-verified content marks for the idlefish conversation list page: the
 * Flutter semantics tree there does not expose the bottom tab bar at all, so
 * parking detection cannot rely on tab forms alone. Conversation entries carry
 * timestamp descriptions ("3小时前", "08-15") and unread badges ("红点提醒").
 */
object DutyPageMarks {
    private val timestamp = Regex("""^(\d+(小时|分钟)前|\d{1,2}-\d{1,2})$""")
    private const val UNREAD_BADGE = "红点提醒"
    private const val MIN_TIMESTAMPS = 2

    fun looksLikeConversationList(root: AccessibilityNodeInfo): Boolean {
        var timestamps = 0
        var badges = 0
        fun visit(node: AccessibilityNodeInfo) {
            val desc = node.contentDescription?.toString()?.trim()
            if (!desc.isNullOrEmpty()) {
                if (timestamp.matches(desc)) timestamps++
                if (desc == UNREAD_BADGE) badges++
            }
            for (index in 0 until node.childCount) node.getChild(index)?.let(::visit)
        }
        visit(root)
        return timestamps >= MIN_TIMESTAMPS || badges >= 1
    }
}
