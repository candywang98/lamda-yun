package com.company.cloudctl.dpc

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Business
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

class DpcActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val controller = PolicyController(this)
        setContent { DpcTheme { DpcScreen(controller) } }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DpcScreen(controller: PolicyController) {
    var status by remember { mutableStateOf(controller.status()) }
    var packages by remember {
        mutableStateOf(
            listOf(PolicyController.COMPANION_PACKAGE, "com.company.authorized.target").joinToString(",\n"),
        )
    }
    var message by remember { mutableStateOf<String?>(null) }
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Business, contentDescription = null)
                        Text("Dedicated device policy", modifier = Modifier.padding(start = 8.dp))
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Card(shape = MaterialTheme.shapes.small, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    StatusRow("Device owner", status.deviceOwner)
                    StatusRow("Admin active", status.adminActive)
                    Text("Managed allowlist: ${status.lockTaskPackages.size}")
                }
            }
            if (!status.deviceOwner) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                    Text(
                        "Not provisioned as a company-owned device owner",
                        modifier = Modifier.padding(start = 8.dp),
                    )
                }
            }
            OutlinedTextField(
                value = packages,
                onValueChange = { packages = it },
                label = { Text("Kiosk package allowlist") },
                minLines = 4,
                modifier = Modifier.fillMaxWidth(),
                enabled = status.deviceOwner,
            )
            Button(
                onClick = {
                    message = runCatching {
                        controller.applyDedicatedDevicePolicy(AllowlistParser.parse(packages))
                        status = controller.status()
                        "Policy applied"
                    }.exceptionOrNull()?.message
                },
                enabled = status.deviceOwner,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Default.Lock, contentDescription = null)
                Text("Apply policy", modifier = Modifier.padding(start = 8.dp))
            }
            OutlinedButton(
                onClick = {
                    message = runCatching {
                        controller.clearDedicatedDevicePolicy()
                        status = controller.status()
                        "Policy released"
                    }.exceptionOrNull()?.message
                },
                enabled = status.deviceOwner,
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Release kiosk policy") }
            message?.let { Text(it) }
        }
    }
}

@Composable
private fun StatusRow(label: String, enabled: Boolean) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                if (enabled) Icons.Default.CheckCircle else Icons.Default.Warning,
                contentDescription = null,
                tint = if (enabled) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
            )
            Text(if (enabled) "Enabled" else "Disabled", modifier = Modifier.padding(start = 6.dp))
        }
    }
}

@Composable
private fun DpcTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = androidx.compose.material3.lightColorScheme(
            primary = Color(0xFF176B53),
            secondary = Color(0xFF315B74),
            tertiary = Color(0xFF80551F),
            background = Color(0xFFF7F9F8),
        ),
        content = content,
    )
}

