package com.company.cloudctl.companion.live

/**
 * K13 live-capabilities/v1@20260917.1 §3 frame-geometry descriptor and the
 * single transform kernel it mandates. The Companion owns the kernel: frame
 * production runs [FrameGeometry.forward] (device -> frame) and remote input
 * execution runs its strict inverse [FrameGeometry.inverse] (frame ->
 * device) — same object, same tables, so the two directions can never drift
 * apart. The Web side only emits frame-space coordinates; the server only
 * relays and never transforms.
 *
 * Spaces (all origins top-left, pixels):
 *  - device space: the display plane in its CURRENT orientation,
 *    (dx in [0, deviceWidth), dy in [0, deviceHeight)) — the coordinate
 *    system dispatchGesture expects.
 *  - intermediate space: the rotated-but-unscaled image,
 *    (u in [0, uw), v in [0, uh)) with
 *    (uw, uh) = rotation in {0, 180} ? (deviceWidth, deviceHeight)
 *                                    : (deviceHeight, deviceWidth).
 *  - frame space: the actual encoded frame pixels,
 *    (fx in [0, frameWidth), fy in [0, frameHeight)) — the space remote
 *    inputs are expressed in.
 *
 * Pure Kotlin, JVM-unit-testable.
 */
data class FrameGeometry(
    val frameWidth: Int,
    val frameHeight: Int,
    val deviceWidth: Int,
    val deviceHeight: Int,
    val rotation: Int,
    val safeArea: SafeAreaRect? = null,
) {
    init {
        require(frameWidth > 0 && frameHeight > 0) { "frame size must be positive" }
        require(deviceWidth > 0 && deviceHeight > 0) { "device size must be positive" }
        require(rotation in ALLOWED_ROTATIONS) { "rotation must be one of $ALLOWED_ROTATIONS" }
    }

    val intermediateWidth: Int
        get() = if (rotation == 0 || rotation == 180) deviceWidth else deviceHeight

    val intermediateHeight: Int
        get() = if (rotation == 0 || rotation == 180) deviceHeight else deviceWidth

    /**
     * Forward (producer) transform: device space -> frame space, continuous
     * coordinates. Rotate by `rotation` into the intermediate space (K13 §3
     * clockwise image rotation), then scale to the frame size.
     */
    fun forward(dx: Double, dy: Double): Pair<Double, Double> {
        val uw = intermediateWidth.toDouble()
        val uh = intermediateHeight.toDouble()
        val u: Double
        val v: Double
        when (rotation) {
            0 -> {
                u = dx
                v = dy
            }
            180 -> {
                u = uw - 1 - dx
                v = uh - 1 - dy
            }
            90 -> {
                u = uw - 1 - dy
                v = dx
            }
            270 -> {
                u = dy
                v = uh - 1 - dx
            }
            else -> error("rotation $rotation not in $ALLOWED_ROTATIONS")
        }
        return (u * frameWidth / uw) to (v * frameHeight / uh)
    }

    /**
     * Strict inverse (K13 §3 input-execution steps), the exact inverse of
     * [forward]:
     *  1. un-scale: u = fx*uw/frameWidth, v = fy*uh/frameHeight;
     *  2. un-rotate by the frozen lookup table;
     *  3. round to device pixels (half-up);
     *  4. a result off the device plane or inside the [safeArea] exclusion
     *     zone is REJECTED — never silently clamped to the screen edge
     *     (K13 §3.4: drop, count, audit).
     */
    fun inverse(fx: Double, fy: Double): GeometryPoint {
        if (fx < 0.0 || fy < 0.0 || fx >= frameWidth.toDouble() || fy >= frameHeight.toDouble()) {
            return GeometryPoint.Rejected(GeometryRejection.OUT_OF_BOUNDS)
        }
        val uw = intermediateWidth.toDouble()
        val uh = intermediateHeight.toDouble()
        val u = fx * uw / frameWidth
        val v = fy * uh / frameHeight
        val dxr: Double
        val dyr: Double
        when (rotation) {
            0 -> {
                dxr = u
                dyr = v
            }
            180 -> {
                dxr = uw - 1 - u
                dyr = uh - 1 - v
            }
            90 -> {
                dxr = v
                dyr = uw - 1 - u
            }
            270 -> {
                dxr = uh - 1 - v
                dyr = u
            }
            else -> error("rotation $rotation not in $ALLOWED_ROTATIONS")
        }
        val dx = Math.round(dxr).toInt()
        val dy = Math.round(dyr).toInt()
        if (dx < 0 || dx >= deviceWidth || dy < 0 || dy >= deviceHeight) {
            return GeometryPoint.Rejected(GeometryRejection.OUT_OF_BOUNDS)
        }
        if (safeArea != null && safeArea.contains(dx, dy)) {
            return GeometryPoint.Rejected(GeometryRejection.SAFE_AREA)
        }
        return GeometryPoint.Mapped(dx, dy)
    }

    companion object {
        val ALLOWED_ROTATIONS = setOf(0, 90, 180, 270)
    }
}

/** Device-space exclusion rect (cutout / notch / system-bar region), half-open. */
data class SafeAreaRect(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
) {
    init {
        require(left >= 0 && top >= 0) { "safe area origin must be non-negative" }
        require(right > left && bottom > top) { "safe area must have positive extent" }
    }

    fun contains(x: Int, y: Int): Boolean = x >= left && x < right && y >= top && y < bottom
}

enum class GeometryRejection { OUT_OF_BOUNDS, SAFE_AREA }

sealed interface GeometryPoint {
    data class Mapped(val dx: Int, val dy: Int) : GeometryPoint

    data class Rejected(val reason: GeometryRejection) : GeometryPoint
}
