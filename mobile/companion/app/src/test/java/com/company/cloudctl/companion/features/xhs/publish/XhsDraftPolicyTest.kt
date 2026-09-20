package com.company.cloudctl.companion.features.xhs.publish

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * F14 验收：草稿弹窗可解释处理；未知旧草稿绝不自动删除。
 */
class XhsDraftPolicyTest {

    @Test
    fun defaultWaitingUserPolicyPausesInsteadOfChoosing() {
        val decision = XhsDraftPolicyEngine.decide(
            policy = XhsDraftPolicy.WAITING_USER,
            dialogShown = true,
            draftIdentity = "旧草稿A",
            createdThisRun = false,
        )
        assertEquals(XhsDraftAction.PAUSE_WAITING_USER, decision.action)
        assertFalse(decision.escalatedToWaitingUser)
        assertTrue(decision.reason.contains("WAITING_USER"))
    }

    @Test
    fun saveDraftPolicySavesExplicitly() {
        val decision = XhsDraftPolicyEngine.decide(
            policy = XhsDraftPolicy.SAVE_DRAFT,
            dialogShown = true,
            draftIdentity = null,
            createdThisRun = false,
        )
        assertEquals(XhsDraftAction.TAP_SAVE_DRAFT, decision.action)
    }

    @Test
    fun discardOnlyAllowedForKnownDraftCreatedThisRun() {
        val allowed = XhsDraftPolicyEngine.decide(
            policy = XhsDraftPolicy.DISCARD_DRAFT,
            dialogShown = true,
            draftIdentity = "本次草稿#1",
            createdThisRun = true,
        )
        assertEquals(XhsDraftAction.TAP_DISCARD, allowed.action)
        assertTrue(allowed.reason.contains("身份匹配"))
    }

    @Test
    fun unknownOldDraftIsNeverAutoDiscardedEvenWithDiscardPolicy() {
        val unknownIdentity = XhsDraftPolicyEngine.decide(
            policy = XhsDraftPolicy.DISCARD_DRAFT,
            dialogShown = true,
            draftIdentity = null,
            createdThisRun = true,
        )
        assertEquals(XhsDraftAction.PAUSE_WAITING_USER, unknownIdentity.action)
        assertTrue(unknownIdentity.escalatedToWaitingUser)
        assertTrue(unknownIdentity.reason.contains("未知旧草稿不自动删除"))

        val notThisRun = XhsDraftPolicyEngine.decide(
            policy = XhsDraftPolicy.DISCARD_DRAFT,
            dialogShown = true,
            draftIdentity = "某个旧草稿",
            createdThisRun = false,
        )
        assertEquals(XhsDraftAction.PAUSE_WAITING_USER, notThisRun.action)
        assertTrue(notThisRun.escalatedToWaitingUser)
    }

    @Test
    fun noDialogIsANoOpPauseWithReason() {
        val decision = XhsDraftPolicyEngine.decide(
            policy = XhsDraftPolicy.SAVE_DRAFT,
            dialogShown = false,
            draftIdentity = null,
            createdThisRun = false,
        )
        assertEquals(XhsDraftAction.PAUSE_WAITING_USER, decision.action)
        assertEquals("no-draft-dialog", decision.reason)
    }
}
