package com.company.cloudctl.companion.live

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * L11 acceptance 5: rotation-aware frame geometry transforms, golden values
 * against the K13 live-capabilities/v1@20260917.1 §3 lookup table, plus the
 * forward∘inverse round trip (the contract mandates ONE shared kernel so the
 * producer transform and the input inverse can never drift).
 */
class FrameGeometryTest {
    private val portrait = FrameGeometry(
        frameWidth = 405,
        frameHeight = 720,
        deviceWidth = 1080,
        deviceHeight = 1920,
        rotation = 0,
    )

    private fun landscape(rotation: Int) = FrameGeometry(
        frameWidth = 720,
        frameHeight = 405,
        deviceWidth = 1920,
        deviceHeight = 1080,
        rotation = rotation,
    )

    @Test
    fun rotationZeroInverseGolden() {
        // K13 §3 inverse table, rotation=0: dx=u, dy=v.
        // Center of a 405x720 frame of a 1080x1920 device -> (540, 960).
        val center = portrait.inverse(202.5, 360.0)
        val mapped = assertIs<GeometryPoint.Mapped>(center)
        assertEquals(540, mapped.dx)
        assertEquals(960, mapped.dy)
        // Exact corners: (0,0) frame -> (0,0) device.
        val origin = assertIs<GeometryPoint.Mapped>(portrait.inverse(0.0, 0.0))
        assertEquals(0, origin.dx)
        assertEquals(0, origin.dy)
        // Bottom-right corner: fx=404 -> u=404*1080/405=1077.3 -> 1077;
        // fy=719 -> v=719*1920/720=1917.3 -> 1917.
        val corner = assertIs<GeometryPoint.Mapped>(portrait.inverse(404.0, 719.0))
        assertEquals(1077, corner.dx)
        assertEquals(1917, corner.dy)
    }

    @Test
    fun rotationNinetyInverseGolden() {
        // K13 lookup, rotation=90: dx = v, dy = (uw-1) - u with
        // uw=intermediateWidth=1080 (device plane 1920x1080 -> intermediate
        // 1080x1920 swapped: uw=1920? No: device 1920x1080, rotation 90 ->
        // (uw, uh) = (deviceHeight, deviceWidth) = (1080, 1920).
        val geometry = landscape(rotation = 90)
        assertEquals(1080, geometry.intermediateWidth)
        assertEquals(1920, geometry.intermediateHeight)
        // Frame center (360, 202.5): u = 360*1080/720 = 540, v = 202.5*1920/405 = 960.
        // dx = v = 960, dy = (uw-1) - u = 1079 - 540 = 539.
        val mapped = assertIs<GeometryPoint.Mapped>(geometry.inverse(360.0, 202.5))
        assertEquals(960, mapped.dx)
        assertEquals(539, mapped.dy)
        // Top-left of the frame: u=0, v=0 -> dx=0, dy=uw-1=1079 (image
        // clockwise rotation moves the frame origin to the device's right edge).
        val origin = assertIs<GeometryPoint.Mapped>(geometry.inverse(0.0, 0.0))
        assertEquals(0, origin.dx)
        assertEquals(1079, origin.dy)
    }

    @Test
    fun rotationOneEightyInverseGolden() {
        // K13 lookup, rotation=180: dx=(uw-1)-u, dy=(uh-1)-v; device 1920x1080
        // -> (uw,uh) = (1920,1080).
        val geometry = landscape(rotation = 180)
        assertEquals(1920, geometry.intermediateWidth)
        assertEquals(1080, geometry.intermediateHeight)
        val mapped = assertIs<GeometryPoint.Mapped>(geometry.inverse(360.0, 202.5))
        // u = 360*1920/720 = 960, v = 202.5*1080/405 = 540.
        // dx = 1919-960 = 959, dy = 1079-540 = 539.
        assertEquals(959, mapped.dx)
        assertEquals(539, mapped.dy)
        val origin = assertIs<GeometryPoint.Mapped>(geometry.inverse(0.0, 0.0))
        assertEquals(1919, origin.dx)
        assertEquals(1079, origin.dy)
    }

    @Test
    fun rotationTwoSeventyInverseGolden() {
        // K13 lookup, rotation=270: dx=(uh-1)-v, dy=u; device 1920x1080 ->
        // (uw,uh) = (1080,1920).
        val geometry = landscape(rotation = 270)
        assertEquals(1080, geometry.intermediateWidth)
        assertEquals(1920, geometry.intermediateHeight)
        val mapped = assertIs<GeometryPoint.Mapped>(geometry.inverse(360.0, 202.5))
        // u = 540, v = 960. dx = (uh-1)-v = 1919-960 = 959, dy = u = 540.
        assertEquals(959, mapped.dx)
        assertEquals(540, mapped.dy)
        val origin = assertIs<GeometryPoint.Mapped>(geometry.inverse(0.0, 0.0))
        assertEquals(1919, origin.dx)
        assertEquals(0, origin.dy)
    }

    @Test
    fun forwardInverseRoundTripAllRotations() {
        // The shared kernel: inverse(forward(p)) == p (within one device
        // pixel of rounding) for interior points at every rotation.
        for (rotation in intArrayOf(0, 90, 180, 270)) {
            val geometry = if (rotation == 0) portrait else landscape(rotation)
            for (dx in listOf(1, 137, 539, 540, 1081)) {
                for (dy in listOf(1, 431, 959, 960, 1877)) {
                    if (dx >= geometry.deviceWidth || dy >= geometry.deviceHeight) continue
                    val (fx, fy) = geometry.forward(dx.toDouble(), dy.toDouble())
                    val back = assertIs<GeometryPoint.Mapped>(geometry.inverse(fx, fy))
                    assertTrue(
                        abs(back.dx - dx) <= 1 && abs(back.dy - dy) <= 1,
                        "rotation=$rotation ($dx,$dy) -> ($fx,$fy) -> (${back.dx},${back.dy})",
                    )
                }
            }
        }
    }

    @Test
    fun offPlaneCoordinatesAreRejectedNotClamped() {
        // K13 §3.4: results off the device plane (or inputs off the frame) are
        // dropped, never silently clamped to the screen edge.
        for (fx in listOf(-0.5, 405.0, 500.0)) {
            val rejected = assertIs<GeometryPoint.Rejected>(portrait.inverse(fx, 100.0))
            assertEquals(GeometryRejection.OUT_OF_BOUNDS, rejected.reason)
        }
        for (fy in listOf(-0.1, 720.0)) {
            val rejected = assertIs<GeometryPoint.Rejected>(portrait.inverse(100.0, fy))
            assertEquals(GeometryRejection.OUT_OF_BOUNDS, rejected.reason)
        }
        // Rounding past the last device pixel also rejects (no clamp).
        val geometry = FrameGeometry(
            frameWidth = 3,
            frameHeight = 3,
            deviceWidth = 4,
            deviceHeight = 4,
            rotation = 0,
        )
        // fx=2.9 -> u=3.87 -> rounds to 4 == deviceWidth -> OUT_OF_BOUNDS.
        val edge = assertIs<GeometryPoint.Rejected>(geometry.inverse(2.9, 1.0))
        assertEquals(GeometryRejection.OUT_OF_BOUNDS, edge.reason)
    }

    @Test
    fun safeAreaExclusionRejectsSystemGestureZone() {
        // Status-bar / gesture-nav strip at the top of the device plane.
        val geometry = portrait.copy(safeArea = SafeAreaRect(left = 0, top = 0, right = 1080, bottom = 96))
        val inSafeArea = assertIs<GeometryPoint.Rejected>(geometry.inverse(202.5, 20.0))
        assertEquals(GeometryRejection.SAFE_AREA, inSafeArea.reason)
        // Just below the strip maps fine.
        val below = assertIs<GeometryPoint.Mapped>(geometry.inverse(202.5, 40.0))
        assertEquals(540, below.dx)
        assertTrue(below.dy >= 96)
    }

    @Test
    fun constructorValidatesClosedSets() {
        assertFailsWith<IllegalArgumentException> {
            FrameGeometry(0, 720, 1080, 1920, 0)
        }
        assertFailsWith<IllegalArgumentException> {
            FrameGeometry(405, 720, 1080, 1920, 45)
        }
        assertFailsWith<IllegalArgumentException> {
            SafeAreaRect(0, 0, 0, 96)
        }
    }
}
