package com.company.cloudctl.companion.automation

object SingleShotDispatchBoundary {
    inline fun dispatch(
        validateImmediatelyBeforeDispatch: () -> Unit,
        canSubmit: () -> Boolean = { true },
        submit: () -> Boolean,
    ): Boolean {
        validateImmediatelyBeforeDispatch()
        if (!canSubmit()) return false
        return submit()
    }
}
