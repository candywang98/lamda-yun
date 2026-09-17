package com.company.cloudctl.companion.locators

/**
 * B13 (fleet-first-20260916.1) — evidence levels for "which published item
 * is this, really". When the platform exposes NO reliable platformItemId,
 * the only admissible identity is the ACCOUNT scope plus a COMPOSITE of
 * visible attributes (title + price / action label / listing state) matched
 * against exactly one card, and even then the evidence level demands human
 * confirmation before anything irreversible runs. Attribute ambiguity (the
 * composite matches zero or several distinct cards) fails closed with a
 * readable reason string — picking first/center/largest is forbidden, same
 * as ui-observation/v1 §3.
 */
object ItemIdentityEvidencePolicy {

    /** Title counts as one attribute; at least one more visible attribute is required. */
    const val MIN_COMPOSITE_ATTRIBUTES = 2

    /**
     * Evaluate the evidence for one candidate item.
     *
     * @param attributes the requested composite (account scope, title
     *   fragment, and whatever other visible attributes the caller can read).
     * @param cardLines the visible text/content-desc lines of the candidate
     *   card(s), used to record which lines actually confirmed the match.
     * @param distinctMatchingCards how many distinct cards on the live page
     *   carry this composite (the locator's collapsed-match count).
     * @param platformItemId the platform's own item id when genuinely
     *   readable or operator-entered; blank/null is treated as absent and is
     *   NEVER fabricated (ui-observation/v1 §4).
     */
    fun evaluate(
        attributes: CompositeItemAttributes,
        cardLines: List<String>,
        distinctMatchingCards: Int,
        platformItemId: String? = null,
    ): ItemIdentityEvidence {
        val realId = platformItemId?.takeIf { it.isNotBlank() }
        if (realId != null) {
            return ItemIdentityEvidence.PlatformItemId(
                itemId = realId,
                accountScope = attributes.accountScope,
            )
        }
        val account = attributes.accountScope?.takeIf { it.isNotBlank() }
            ?: return ItemIdentityEvidence.Insufficient(
                reason = "no reliable platformItemId and no account scope: identity would be page-global, " +
                    "not account-scoped; refusing to select",
            )
        if (attributes.titleContains.isBlank()) {
            return ItemIdentityEvidence.Insufficient(
                reason = "composite identity requires a non-blank title fragment",
            )
        }
        if (distinctMatchingCards == 0) {
            return ItemIdentityEvidence.Insufficient(
                reason = "composite attributes match ZERO distinct cards " +
                    "(title='${attributes.titleContains}'); nothing to confirm",
            )
        }
        if (distinctMatchingCards > 1) {
            return ItemIdentityEvidence.Insufficient(
                reason = "attribute ambiguity: composite (title='${attributes.titleContains}', " +
                    "price=${attributes.price ?: "—"}, action=${attributes.actionLabel ?: "—"}) matches " +
                    "$distinctMatchingCards distinct cards; auto-selecting one is forbidden — " +
                    "disambiguate the title or stop",
            )
        }
        if (attributes.visibleAttributeCount < MIN_COMPOSITE_ATTRIBUTES) {
            return ItemIdentityEvidence.Insufficient(
                reason = "composite identity needs ≥$MIN_COMPOSITE_ATTRIBUTES visible attributes, got " +
                    "${attributes.visibleAttributeCount} (title alone is not an identity)",
            )
        }
        val wanted = listOfNotNull(
            attributes.titleContains,
            attributes.price,
            attributes.actionLabel,
            attributes.listingState,
        )
        val confirming = cardLines.filter { line -> wanted.any { line.contains(it) } }
        return ItemIdentityEvidence.CompositeConfirmed(
            attributes = attributes.copy(accountScope = account),
            confirmingLines = confirming,
            distinctMatchingCards = distinctMatchingCards,
        )
    }
}

/** The composite visible attributes of a candidate item (no platformItemId path). */
data class CompositeItemAttributes(
    /** The account whose published list is on screen; identity is account-scoped, never page-global. */
    val accountScope: String?,
    val titleContains: String,
    val price: String? = null,
    /** The card action label that will be tapped (编辑 / 托管 / 降价 / 诊断 / 删除 / 重新上架). */
    val actionLabel: String? = null,
    /** 在卖 / 已下架 — the tab the card was found under. */
    val listingState: String? = null,
) {
    /** Title always counts; each further non-null visible attribute adds one. */
    val visibleAttributeCount: Int
        get() = 1 + listOfNotNull(price, actionLabel, listingState).size
}

/** Ordered evidence levels; higher is stronger. */
enum class EvidenceLevel {
    /** The platform's own id, genuinely readable or operator-entered. */
    PLATFORM_ITEM_ID,

    /** Account + composite visible attributes + human confirmation gate. */
    COMPOSITE_HUMAN_CONFIRMED,

    /** Not enough evidence to act; the reason string says why. */
    INSUFFICIENT,
}

sealed interface ItemIdentityEvidence {
    val level: EvidenceLevel

    data class PlatformItemId(
        val itemId: String,
        val accountScope: String?,
    ) : ItemIdentityEvidence {
        override val level: EvidenceLevel get() = EvidenceLevel.PLATFORM_ITEM_ID
    }

    /**
     * Account-scoped composite matched exactly one card. This is a WEAKER
     * level than a platform id by construction: [humanConfirmationRequired]
     * is always true and must gate any irreversible action downstream.
     */
    data class CompositeConfirmed(
        val attributes: CompositeItemAttributes,
        val confirmingLines: List<String>,
        val distinctMatchingCards: Int,
    ) : ItemIdentityEvidence {
        override val level: EvidenceLevel get() = EvidenceLevel.COMPOSITE_HUMAN_CONFIRMED
        val humanConfirmationRequired: Boolean get() = true
    }

    /** Fail-closed verdict with the readable reason. */
    data class Insufficient(val reason: String) : ItemIdentityEvidence {
        override val level: EvidenceLevel get() = EvidenceLevel.INSUFFICIENT
    }
}
