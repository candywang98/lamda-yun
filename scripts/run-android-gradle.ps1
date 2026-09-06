param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("companion", "dpc")]
    [string]$Project,

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$GradleArguments = @("tasks")
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$projectDirectory = Join-Path $repositoryRoot "mobile\$Project"
$wrapperProperties = Join-Path $projectDirectory "gradle\wrapper\gradle-wrapper.properties"
$wrapperJar = Join-Path $projectDirectory "gradle\wrapper\gradle-wrapper.jar"
$projectProperties = Join-Path $projectDirectory "gradle.properties"

if (-not $env:JAVA_HOME) {
    throw "JAVA_HOME must point to a JDK 17 installation."
}
$java = Join-Path $env:JAVA_HOME "bin\java.exe"
if (-not (Test-Path -LiteralPath $java -PathType Leaf)) {
    throw "JAVA_HOME does not contain bin\java.exe: $env:JAVA_HOME"
}

$distributionLine = Get-Content -LiteralPath $wrapperProperties |
    Where-Object { $_ -like "distributionUrl=*" } |
    Select-Object -First 1
if ($distributionLine -notmatch "gradle-(?<version>[0-9.]+)-bin\.zip") {
    throw "Unable to determine the Gradle version from $wrapperProperties"
}
$gradleVersion = $Matches.version
$distributionRoot = Join-Path $env:USERPROFILE ".gradle\wrapper\dists\gradle-$gradleVersion-bin"
$gradleHome = Get-ChildItem -LiteralPath $distributionRoot -Directory -ErrorAction Stop |
    ForEach-Object { Join-Path $_.FullName "gradle-$gradleVersion" } |
    Where-Object { Test-Path -LiteralPath $_ -PathType Container } |
    Select-Object -First 1
if (-not $gradleHome) {
    throw "Gradle $gradleVersion is not present in the Wrapper cache. Run gradlew.bat --version first."
}

$instrumentationAgent = Join-Path $gradleHome (
    "lib\agents\gradle-instrumentation-agent-$gradleVersion.jar"
)
if (-not (Test-Path -LiteralPath $instrumentationAgent -PathType Leaf)) {
    throw "Gradle instrumentation agent is missing: $instrumentationAgent"
}

$jvmArgs = @(
    "--add-opens=java.base/java.util=ALL-UNNAMED",
    "--add-opens=java.base/java.lang=ALL-UNNAMED",
    "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED",
    "--add-opens=java.prefs/java.util.prefs=ALL-UNNAMED",
    "--add-exports=jdk.compiler/com.sun.tools.javac.api=ALL-UNNAMED",
    "--add-exports=jdk.compiler/com.sun.tools.javac.util=ALL-UNNAMED",
    "--add-opens=java.base/java.nio.charset=ALL-UNNAMED",
    "--add-opens=java.base/java.net=ALL-UNNAMED",
    "--add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED",
    "-Duser.country=CN",
    "-Duser.language=zh",
    "-Duser.variant",
    "-javaagent:$instrumentationAgent",
    "-Dorg.gradle.appname=gradlew"
)

$configuredJvmArgs = Get-Content -LiteralPath $projectProperties |
    Where-Object { $_ -like "org.gradle.jvmargs=*" } |
    Select-Object -First 1
if ($configuredJvmArgs) {
    $jvmArgs += $configuredJvmArgs.Substring("org.gradle.jvmargs=".Length).Split(
        " ",
        [System.StringSplitOptions]::RemoveEmptyEntries
    )
}

$jvmArgs += @(
    "-classpath",
    $wrapperJar,
    "org.gradle.wrapper.GradleWrapperMain",
    "--no-daemon"
)
if (-not $GradleArguments -or $GradleArguments.Count -eq 0) {
    $GradleArguments = @("tasks")
}

Push-Location $projectDirectory
try {
    & $java @jvmArgs @GradleArguments
    $result = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $result
