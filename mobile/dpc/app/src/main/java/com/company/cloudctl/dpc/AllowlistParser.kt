package com.company.cloudctl.dpc

object AllowlistParser {
    private val packageName = Regex("^[a-zA-Z][a-zA-Z0-9_]*(\\.[a-zA-Z][a-zA-Z0-9_]*)+$")

    fun parse(value: String): List<String> {
        val packages = value.split(',', '\n').map(String::trim).filter(String::isNotEmpty).distinct()
        require(packages.isNotEmpty()) { "At least one kiosk package is required" }
        require(packages.all(packageName::matches)) { "Kiosk allowlist contains an invalid package" }
        return packages
    }
}

