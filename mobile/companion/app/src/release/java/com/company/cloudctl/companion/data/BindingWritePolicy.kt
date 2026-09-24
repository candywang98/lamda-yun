package com.company.cloudctl.companion.data

/** Release variant. Enrollment still saves a binding and starts sync. */
internal object BindingWritePolicy {
    fun beforeSave() = Unit
}
