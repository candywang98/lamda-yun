package com.company.cloudctl.companion.ime

/**
 * The one field-proof the accessibility service may hand to a later reader.
 *
 * [replace] clears the slot before [write] runs. If [write] throws, or returns
 * null, the slot stays empty. A reader cannot observe the previous proof after
 * a new write has started.
 */
internal class FieldProofSlot<T> {
    private var value: T? = null

    fun current(): T? = value

    /**
     * [write] is suspend because the service's replace is. A non-suspend lambda
     * cannot call it. The slot is cleared before the first suspension point
     * inside [write], and a throw leaves it empty.
     */
    suspend fun replace(write: suspend () -> T?): T? {
        value = null
        val minted = write()
        value = minted
        return minted
    }
}
