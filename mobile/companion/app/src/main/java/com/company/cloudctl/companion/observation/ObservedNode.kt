package com.company.cloudctl.companion.observation

import org.json.JSONObject

/**
 * ui-observation/v1@20260916.1 §2 — one node of an Observation tree.
 *
 * `depth`/`index` are the canonical ordering keys (nodes are stably sorted by
 * `(depth, index)` before canonicalization); the six identity fields
 * (`class`, `resourceId`, `text`, `contentDesc`, `bounds`, `clickable`) are
 * the only fields that enter [CanonicalTree]. `class` and `package` are
 * Kotlin keywords, so the JSON keys map to `className`/`packageName`.
 *
 * All six identity fields are REQUIRED — a node missing any of them cannot be
 * canonicalized and therefore cannot participate in a treeDigest equality
 * assertion (fail-closed, mirroring the Python checker's KeyError).
 */
data class ObservedNode(
    val depth: Int,
    val index: Int,
    val className: String,
    val resourceId: String,
    val text: String,
    val contentDesc: String,
    val bounds: Bounds,
    val clickable: Boolean,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("depth", depth)
        .put("index", index)
        .put("class", className)
        .put("resourceId", resourceId)
        .put("text", text)
        .put("contentDesc", contentDesc)
        .put("bounds", bounds.wire)
        .put("clickable", clickable)

    companion object {
        fun fromJson(json: JSONObject): ObservedNode {
            val required = listOf(
                "depth", "index", "class", "resourceId", "text",
                "contentDesc", "bounds", "clickable",
            )
            for (key in required) {
                require(json.has(key)) { "observed node missing required field '$key'" }
            }
            require(json.get("clickable") is Boolean) {
                "observed node field 'clickable' must be a JSON boolean (lowercase in canonical form)"
            }
            return ObservedNode(
                depth = json.getInt("depth"),
                index = json.getInt("index"),
                className = json.getString("class"),
                resourceId = json.getString("resourceId"),
                text = json.getString("text"),
                contentDesc = json.getString("contentDesc"),
                bounds = Bounds.parse(json.getString("bounds")),
                clickable = json.getBoolean("clickable"),
            )
        }
    }
}

/**
 * Accessibility node bounds in the frozen `left,top,right,bottom` wire format.
 * Geometric helpers power the P09-13 anti-misselect wrapper rule (§3) and the
 * banner-displacement replay (§6).
 */
data class Bounds(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
) {
    val wire: String get() = "$left,$top,$right,$bottom"
    val width: Int get() = right - left
    val height: Int get() = bottom - top
    val area: Long get() = width.toLong() * height.toLong()

    /** True when [other] lies entirely inside this box (edges may coincide). */
    fun contains(other: Bounds): Boolean =
        left <= other.left && top <= other.top &&
            right >= other.right && bottom >= other.bottom

    /**
     * True when this box contains [other] AND is strictly larger — the
     * full-height-wrapper containment signal used to exclude list wrappers.
     */
    fun strictlyContains(other: Bounds): Boolean =
        this != other && contains(other) && area > other.area

    /** This box translated vertically by [dy] (banner/keyboard displacement). */
    fun translated(dy: Int): Bounds = Bounds(left, top + dy, right, bottom + dy)

    companion object {
        fun parse(wire: String): Bounds {
            val parts = wire.split(",")
            require(parts.size == 4) { "bounds must be 'left,top,right,bottom': $wire" }
            val ints = parts.map { part ->
                part.trim().toIntOrNull()
                    ?: throw IllegalArgumentException("non-integer bounds component '$part' in: $wire")
            }
            return Bounds(ints[0], ints[1], ints[2], ints[3])
        }
    }
}

/** Screen insets captured with the snapshot (§2; values in pixels). */
data class Insets(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("left", left)
        .put("top", top)
        .put("right", right)
        .put("bottom", bottom)

    companion object {
        fun fromJson(json: JSONObject): Insets = Insets(
            json.getInt("left"),
            json.getInt("top"),
            json.getInt("right"),
            json.getInt("bottom"),
        )
    }
}
