package com.company.cloudctl.companion.automation

import java.util.concurrent.ConcurrentHashMap

/**
 * Per-task badge snapshots for the xianyu maintenance gate.
 *
 * The first strike (··· menu / delete button) runs before any dialog covers the
 * published-goods tabs, so the executor records the affected badge there. The
 * destructive confirm fires later, with the centered dialog hiding the tab bar
 * from the semantics tree (device-verified BADGE_UNREADABLE), so the gate reads
 * the authoritative baseline from this snapshot instead of a live inspect.
 *
 * A device has one active runner, so per-taskId entries never race; entries are
 * cleared when the executor finishes the task.
 */
internal object MaintenanceBadgeSnapshots {
    private val snapshots = ConcurrentHashMap<String, Int>()

    fun record(taskId: String, badgeRef: String, value: Int) {
        snapshots["$taskId|$badgeRef"] = value
    }

    fun take(taskId: String, badgeRef: String): Int? = snapshots["$taskId|$badgeRef"]

    fun clear(taskId: String) {
        snapshots.keys.removeAll { it.startsWith("$taskId|") }
    }
}
