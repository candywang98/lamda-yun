package com.company.cloudctl.companion.observation

import java.io.File

/**
 * B12 test-side fixture access.
 *
 * Fixtures live canonically in the repo at `tests/fixtures/ui-replay/`
 * (same-source copies of the frozen K11 contract fixtures plus derived
 * replay fixtures) and are mirrored byte-identically onto the unit-test
 * classpath at `ui-replay/…` (src/test/resources). The frozen originals stay
 * at `contracts/ui-observation/v1/fixtures/`. Tests load BOTH copies and
 * assert they are byte-identical — nobody may drift a fixture silently.
 */
object FixturePaths {
    const val CONTRACT_ID = "ui-observation/v1@20260916.1"

    val contractFixtureNames = listOf(
        "k11-positive-observation.json",
        "k11-negative-samename-ambiguous.json",
        "k11-negative-fullheight-wrapper.json",
        "k11-negative-banner-displacement.json",
        "k11-negative-input-redraw-lost.json",
    )

    val replayFixtureNames = listOf(
        "b12-samename-ambiguous.json",
        "b12-fullheight-wrapper.json",
        "b12-banner-displacement.json",
    )

    /** Repo root located by walking up from CWD (same convention as the P09 golden test). */
    fun repoRoot(): File = generateSequence(File(".").canonicalFile) { it.parentFile }
        .first { File(it, "contracts/ui-observation/v1/tools/check_fixtures.py").isFile }

    fun repoContractFixture(name: String): File =
        File(repoRoot(), "contracts/ui-observation/v1/fixtures/$name")

    fun repoUiReplay(relative: String): File =
        File(repoRoot(), "tests/fixtures/ui-replay/$relative")

    fun classpathText(path: String): String =
        requireNotNull(
            FixturePaths::class.java.classLoader.getResourceAsStream(path)?.readBytes(),
        ) { "classpath fixture not found: $path" }.toString(Charsets.UTF_8)

    fun classpathUiReplay(relative: String): String = classpathText("ui-replay/$relative")
}
