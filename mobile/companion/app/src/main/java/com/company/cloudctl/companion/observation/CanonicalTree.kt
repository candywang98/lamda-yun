package com.company.cloudctl.companion.observation

import java.security.MessageDigest

/**
 * ui-observation/v1@20260916.1 §2 — FROZEN canonical_tree / digest rules.
 *
 * Byte-for-byte port of the contract's reference implementation
 * `contracts/ui-observation/v1/tools/check_fixtures.py` (cross-language
 * golden parity is pinned by tests against the digests frozen into
 * `k11-positive-observation.json`):
 *
 * 1. nodes are stably sorted by `(depth, index)`;
 * 2. every node contributes one `k=v` line per identity field, fields in
 *    alphabetical key order — bounds, class, clickable, contentDesc,
 *    resourceId, text (`sorted(NODE_FIELDS)` in the Python checker);
 * 3. booleans render lowercase (`true`/`false`), strings render as-is;
 * 4. lines are joined with `\n` (no trailing newline);
 * 5. `digest = sha256(utf8(canonical_text))` as lowercase hex.
 *
 * Any change here changes treeDigest and breaks the frozen fixtures — it is
 * an interface, not an implementation detail.
 */
object CanonicalTree {
    /** Alphabetical order of the six identity-field keys (`sorted(NODE_FIELDS)`). */
    val NODE_FIELD_ORDER: List<String> = listOf(
        "bounds", "class", "clickable", "contentDesc", "resourceId", "text",
    )

    /** Canonical `k=v` lines of a single node, in frozen field order. */
    fun nodeLines(node: ObservedNode): List<String> = listOf(
        "bounds=${node.bounds.wire}",
        "class=${node.className}",
        "clickable=${if (node.clickable) "true" else "false"}",
        "contentDesc=${node.contentDesc}",
        "resourceId=${node.resourceId}",
        "text=${node.text}",
    )

    /**
     * Canonical tree text: nodes stably sorted by (depth, index), each node's
     * lines concatenated, `\n`-joined, no trailing newline.
     */
    fun canonicalTree(nodes: List<ObservedNode>): String =
        nodes.sortedWith(compareBy({ it.depth }, { it.index }))
            .flatMap(::nodeLines)
            .joinToString("\n")

    /** sha256 of UTF-8 bytes as lowercase hex (matches Python `hexdigest()`). */
    fun digest(text: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(text.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

    /** §2 `treeDigest = sha256(canonical_tree(nodes))`. */
    fun treeDigest(nodes: List<ObservedNode>): String = digest(canonicalTree(nodes))

    /**
     * Per-node digest used by IdentityProof.nodeDigest (§4). Same convention
     * as the Python checker: the node's own canonical `k=v` lines, digested.
     */
    fun nodeDigest(node: ObservedNode): String = digest(nodeLines(node).joinToString("\n"))
}
