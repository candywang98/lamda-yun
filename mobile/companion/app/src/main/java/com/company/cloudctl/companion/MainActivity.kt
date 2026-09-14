package com.company.cloudctl.companion

import android.Manifest
import android.content.pm.PackageManager
import android.content.Intent
import android.provider.Settings
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Link
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.StopCircle
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.company.cloudctl.companion.model.CompanionState
import com.company.cloudctl.companion.model.ArtifactDeliveryState
import com.company.cloudctl.companion.model.ArtifactKind
import com.company.cloudctl.companion.model.AuthorizedTaskState
import com.company.cloudctl.companion.model.ConfirmationRiskLevel
import com.company.cloudctl.companion.model.ServiceState
import com.company.cloudctl.companion.operations.OperationCatalog
import com.company.cloudctl.companion.operations.OperationDefinition
import com.company.cloudctl.companion.operations.OperationKind
import com.company.cloudctl.companion.service.BatteryOptimization
import com.company.cloudctl.companion.service.BatteryOptimizationPolicy

class MainActivity : ComponentActivity() {
    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent {
            CloudCtlTheme {
                val model: CompanionViewModel = viewModel()
                val state by model.state.collectAsStateWithLifecycle()
                val lifecycleOwner = LocalLifecycleOwner.current
                DisposableEffect(lifecycleOwner, model) {
                    val observer = LifecycleEventObserver { _, event ->
                        if (event == Lifecycle.Event.ON_RESUME) model.refresh()
                    }
                    lifecycleOwner.lifecycle.addObserver(observer)
                    onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
                }
                CompanionScreen(state, model)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CompanionScreen(state: CompanionState, model: CompanionViewModel) {
    val canEmergencyStop = state.binding != null && state.task?.state in setOf(
        AuthorizedTaskState.Running,
        AuthorizedTaskState.WaitingConfirmation,
    )
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("CloudCtl 控制台", color = Color.White, fontWeight = FontWeight.SemiBold)
                        Text(
                            state.binding?.deviceId ?: "未入网设备",
                            style = MaterialTheme.typography.labelMedium,
                            color = Color.White.copy(alpha = 0.78f),
                        )
                    }
                },
                actions = {
                    if (state.binding != null) {
                        IconButton(onClick = model::refresh, enabled = !state.busy) {
                            Icon(Icons.Default.Refresh, tint = Color.White, contentDescription = "Refresh status")
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color(0xFF079B8E),
                ),
            )
        },
        bottomBar = {
            if (canEmergencyStop) {
                Button(
                    onClick = model::emergencyStop,
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error,
                    ),
                ) {
                    Icon(Icons.Default.StopCircle, contentDescription = "Stop automation")
                    Text("停止自动化", modifier = Modifier.padding(start = 8.dp))
                }
            }
        },
    ) { padding ->
        Box(
            Modifier
                .fillMaxSize()
                .semantics { contentDescription = "companion_home_root" }
                .padding(padding),
        ) {
            if (state.binding == null) EnrollmentForm(state.busy, state.error, model)
            else StatusContent(state, model)
            if (state.busy) CircularProgressIndicator(Modifier.align(Alignment.Center))
        }
    }
}

@Composable
private fun EnrollmentForm(busy: Boolean, error: String?, model: CompanionViewModel) {
    var code by remember { mutableStateOf("") }
    // Preconfigured staging server settings
    val defaultCloudUrl = "https://43.133.243.154.sslip.io"
    val defaultFingerprint = "fe178c22ba4327c0a71cdd0c7561654fb76ff67c02aa5461f076bf2fc60622d1"
    
    Column(
        modifier = Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            "设备入网",
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.semantics {
                contentDescription = "Device enrollment Device health Permissions"
            },
        )
        if (!error.isNullOrBlank()) {
            Text(error, color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.SemiBold)
        }
        Section("本机执行器") {
            StatusRow("执行模式", "独立 APK 本地执行")
            StatusRow("应用包名", "com.company.cloudctl.companion")
        }
        Section("云端连接") {
            StatusRow("服务器地址", defaultCloudUrl)
            StatusRow("TLS 指纹", "${defaultFingerprint.take(16)}...")
        }
        OutlinedTextField(
            value = code,
            onValueChange = { code = it.uppercase() },
            label = { Text("入网码") },
            placeholder = { Text("输入 12 位入网码") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = { model.enroll(defaultCloudUrl, code, defaultFingerprint) },
            enabled = !busy && code.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Icon(Icons.Default.Link, contentDescription = "Bind device")
            Text("绑定设备", modifier = Modifier.padding(start = 8.dp))
        }
    }
}

@Composable
private fun StatusContent(state: CompanionState, model: CompanionViewModel) {
    var selectedTab by rememberSaveable { mutableStateOf(CompanionStatusTab.CommonFeatures) }
    val context = LocalContext.current
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        CurrentRunStrip(state)
        AccountAuthorizationPanel(state)
        if (!state.permissions.lamdaServiceCertificateEnabled) {
            KeepAlivePrompt(
                title = "无障碍执行器未开启",
                detail = "开启后才能执行手机自动化任务",
                action = "去开启",
                onClick = {
                    context.startActivity(
                        Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                    )
                },
            )
        }
        if (!state.permissions.inputMethodEnabled || !state.permissions.inputMethodCurrent) {
            KeepAlivePrompt(
                title = if (!state.permissions.inputMethodEnabled) "自动化输入法未启用" else "自动化输入法未设为当前键盘",
                detail = "闲鱼发布与聊天回复需要 CloudCtl Input。未选中时，聊天回复将安全停止。",
                action = "去设置",
                onClick = {
                    if (state.permissions.inputMethodEnabled) {
                        context.getSystemService(android.view.inputmethod.InputMethodManager::class.java)
                            ?.showInputMethodPicker()
                    } else {
                        context.startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
                    }
                },
            )
        }
        if (BatteryOptimizationPolicy.shouldPrompt(state.binding != null, state.permissions.batteryOptimizationIgnored)) {
            KeepAlivePrompt(
                title = "后台省电未放开",
                detail = "请把本应用设为忽略电池优化，小米/华为请再选无限制后台，否则心跳会被冻停",
                action = "去设置",
                onClick = { context.startActivity(BatteryOptimization.settingsIntent(context)) },
            )
        }
        state.error?.let { StatusBanner(it, MaterialTheme.colorScheme.errorContainer, Icons.Default.Warning) }
        if (state.emergencyStopped) {
            StatusBanner("Automation stopped by operator", MaterialTheme.colorScheme.errorContainer, Icons.Default.StopCircle)
        }
        state.confirmation?.let { request ->
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(request.title, fontWeight = FontWeight.SemiBold)
                    StatusRow("Risk", request.riskLevel.label())
                    Text(request.detail, style = MaterialTheme.typography.bodyMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { model.answerConfirmation(true) }) { Text("Confirm") }
                        OutlinedButton(onClick = { model.answerConfirmation(false) }) { Text("Reject") }
                    }
                }
            }
        }
        TabRow(
            selectedTabIndex = selectedTab.ordinal,
            containerColor = Color(0xFF079B8E),
            contentColor = Color.White,
        ) {
            CompanionStatusTab.entries.forEach { tab ->
                Tab(
                    selected = tab == selectedTab,
                    onClick = { selectedTab = tab },
                    text = { Text(tab.label) },
                )
            }
        }
        when (selectedTab) {
            CompanionStatusTab.Environment -> EnvironmentStatus(state, model)
            CompanionStatusTab.CommonFeatures -> AutomationStatus(state, model)
            CompanionStatusTab.OtherEnvironment -> OtherEnvironmentStatus(state, model)
            CompanionStatusTab.Logs -> LogStatus(state)
        }
        OutlinedButton(onClick = model::unbind, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
            Text("解除设备绑定")
        }
        Spacer(Modifier.height(88.dp))
    }
}

@Composable
private fun AccountAuthorizationPanel(state: CompanionState) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("账号授权状态", fontWeight = FontWeight.SemiBold)
            if (state.accountStatuses.isEmpty()) {
                Text("当前设备没有可显示的账号授权记录")
            } else {
                state.accountStatuses.forEach { account ->
                    val status = when {
                        !account.boundToDevice -> "未绑定此设备"
                        account.authorized -> "已授权"
                        else -> "不可用：${account.status}"
                    }
                    StatusRow(account.displayLabel, "${account.platform} · $status")
                }
            }
        }
    }
}

@Composable
private fun CurrentRunStrip(state: CompanionState) {
    val latest = state.localOperations.firstOrNull()
    Surface(color = Color(0xFFE9F7F5), modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text("当前运行", style = MaterialTheme.typography.labelMedium, color = Color(0xFF08766D))
                Text(
                    latest?.let { "${it.title} · ${it.state.userLabel()}" } ?: state.task?.step?.ifBlank { "等待任务" } ?: "等待任务",
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                )
            }
            Text(
                if (state.presenceOnline) "在线" else "离线",
                color = if (state.presenceOnline) Color(0xFF08766D) else Color(0xFF9A5B00),
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

private enum class CompanionStatusTab(val label: String) {
    Environment("基础环境"),
    CommonFeatures("常用功能"),
    OtherEnvironment("其他环境"),
    Logs("运行日志"),
}

@Composable
private fun EnvironmentStatus(state: CompanionState, model: CompanionViewModel) {
    val context = LocalContext.current
    Section("本机执行器") {
        StatusRow("执行模式", "独立 APK 本地执行")
        StatusRow("应用包名", "com.company.cloudctl.companion")
        StatusRow("无障碍执行器", if (state.permissions.lamdaServiceCertificateEnabled) "已启用" else "需要授权")
        StatusRow(
            "自动化输入法",
            when {
                state.permissions.inputMethodCurrent -> "当前键盘"
                state.permissions.inputMethodEnabled -> "已启用，未设为当前"
                else -> "需要授权"
            },
        )
        if (!state.permissions.lamdaServiceCertificateEnabled) {
            Button(
                onClick = {
                    context.startActivity(
                        Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                    )
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("开启无障碍服务")
            }
        }
        if (!state.permissions.inputMethodEnabled || !state.permissions.inputMethodCurrent) {
            Button(
                onClick = {
                    if (state.permissions.inputMethodEnabled) {
                        context.getSystemService(android.view.inputmethod.InputMethodManager::class.java)
                            ?.showInputMethodPicker()
                    } else {
                        context.startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (!state.permissions.inputMethodEnabled) "启用 CloudCtl Input" else "设为当前输入法")
            }
        }
    }
    Section("云端连接") {
        StatusRow("控制 API", if (state.binding != null) "已绑定" else "离线")
        StatusRow("绑定 ID", state.binding?.bindingId.orEmpty())
        StatusRow("当前任务", state.task?.taskRunId ?: "等待任务")
    }
    Section("设备状态") {
        StatusRow("电量", "${state.health.batteryPercent}%${if (state.health.charging) "（充电中）" else ""}")
        StatusRow("网络", state.health.network)
        StatusRow(
            "温度",
            state.health.temperatureCelsius?.let { "%.1f C".format(it) } ?: "未提供",
        )
        StatusRow("执行器版本", state.health.executorVersion)
        StatusRow("可用存储", formatBytes(state.health.freeStorageBytes))
    }
    Section("本机权限") {
        StatusRow("Permissions", if (state.permissions.notificationsGranted) "已允许" else "需要授权")
        StatusRow("Device health", "${state.health.batteryPercent}% · ${state.health.network}")
        StatusRow("通知", if (state.permissions.notificationsGranted) "已允许" else "需要授权")
        StatusRow("电池优化", if (state.permissions.batteryOptimizationIgnored) "已忽略" else "需要放开")
        StatusRow("运行配置", state.permissions.automationProfile)
        StatusRow("Companion", state.health.companionVersion)
        if (BatteryOptimizationPolicy.shouldPrompt(state.binding != null, state.permissions.batteryOptimizationIgnored)) {
            Button(
                onClick = { context.startActivity(BatteryOptimization.settingsIntent(context)) },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("忽略电池优化")
            }
        }
    }
    Section("运行开关") {
        OperationToggle(OperationCatalog.toggles[0], model)
        OperationToggle(OperationCatalog.toggles[1], model)
        OperationToggle(OperationCatalog.toggles[2], model)
        OperationToggle(OperationCatalog.toggles[3], model)
    }
}

@Composable
private fun AutomationStatus(state: CompanionState, model: CompanionViewModel) {
    Section("基础功能") {
        OperationGrid(OperationCatalog.basic, model)
    }
    Section("常用操作") {
        OperationCatalog.common.filter { it.kind == OperationKind.Toggle }.forEach { operation ->
            OperationToggle(operation, model)
        }
        OperationGrid(OperationCatalog.common.filter { it.kind == OperationKind.Action }, model)
    }
    Section("转转功能") {
        OperationGrid(OperationCatalog.marketplace, model)
    }
    Section("红薯功能") {
        OperationGrid(OperationCatalog.content, model)
    }
    Section("任务队列") {
        val task = state.task
        if (task == null) {
            StatusRow("状态", "任务队列正常，等待任务")
            StatusRow("Authorized task", "等待任务")
            StatusRow("Cancellable", "不可以")
        } else {
            StatusRow("任务运行", task.taskRunId)
            StatusRow("状态", task.state.label())
            StatusRow("当前步骤", task.step.ifBlank { "尚未上报" })
            StatusRow("可取消", if (task.cancellable) "可以" else "不可以")
            StatusRow("Cancellable", if (task.cancellable) "可以" else "不可以")
            StatusRow("Authorized task", task.state.label())
            task.confirmationId?.let { StatusRow("人工确认", it) }
        }
    }
    Section("Artifact delivery") {
        StatusRow("状态", if (state.deliveries.isEmpty()) "没有进行中的交付" else "交付中")
    }
    Section("文件交付") {
        if (state.deliveries.isEmpty()) {
            StatusRow("APK / 素材", "没有进行中的交付")
        } else {
            state.deliveries.forEach { delivery ->
                StatusRow(
                    delivery.kind.label(),
                    "${delivery.state.label()} ${delivery.progressPercent}%",
                )
                LinearProgressIndicator(
                    progress = { delivery.progressPercent / 100f },
                    modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                )
                delivery.errorCode?.let { StatusRow("交付错误", it) }
            }
        }
    }
    Section("应用更新") {
        StatusRow("已安装", state.update.currentVersion)
        StatusRow("可用版本", state.update.availableVersion ?: "已是最新")
        StatusRow("签名", if (state.update.signerVerified) "已验证" else "没有批准的更新")
    }
}

@Composable
private fun OtherEnvironmentStatus(state: CompanionState, model: CompanionViewModel) {
    Section("可扩展操作") {
        OperationGrid(OperationCatalog.other, model)
    }
    Section("离线执行") {
        StatusRow("本地队列", "SQLite 持久化")
        StatusRow("断网策略", "继续执行已领取任务")
        StatusRow("回传策略", "联网后按序补传")
        StatusRow("当前网络", state.health.network)
    }
    Section("安全边界") {
        StatusRow("执行包", "com.company.cloudctl.companion")
        StatusRow("指令来源", "编译进 APK 的结构化指令")
        StatusRow("外部控制", "不依赖 ADB / USB / Edge")
    }
}

@Composable
private fun LogStatus(state: CompanionState) {
    Section("本地执行日志") {
        if (state.logs.isEmpty()) {
            StatusRow("状态", "没有本地任务事件")
        } else {
            state.logs.takeLast(12).asReversed().forEach { log ->
                StatusRow(
                    log.stepId ?: log.taskId.take(8),
                    "${log.state} · ${log.detailCode}",
                )
            }
        }
    }
    Section("按钮占位队列") {
        if (state.localOperations.isEmpty()) {
            StatusRow("状态", "尚未点击占位功能")
        } else {
            state.localOperations.take(12).forEach { operation ->
                StatusRow(operation.title, "${operation.state.userLabel()} · ${operation.detail}")
            }
        }
    }
}

@Composable
private fun OperationGrid(operations: List<OperationDefinition>, model: CompanionViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        operations.chunked(4).forEach { rowOperations ->
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                rowOperations.forEach { operation ->
                    Button(
                        onClick = { model.enqueuePlaceholderOperation(operation) },
                        modifier = Modifier.weight(1f).height(56.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFFE7E9EA),
                            contentColor = Color(0xFF242729),
                        ),
                        shape = MaterialTheme.shapes.small,
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 2.dp),
                    ) {
                        Text(
                            operation.title,
                            textAlign = TextAlign.Center,
                            maxLines = 1,
                            fontSize = 12.sp,
                            lineHeight = 16.sp,
                        )
                    }
                }
                if (rowOperations.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun OperationToggle(operation: OperationDefinition, model: CompanionViewModel) {
    var checked by rememberSaveable(operation.key) { mutableStateOf(model.toggleState(operation.key)) }
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f).padding(end = 12.dp)) {
            Text(
                operation.title,
                fontWeight = FontWeight.Medium,
                fontSize = 16.sp,
                lineHeight = 20.sp,
                maxLines = 1,
            )
        }
        Switch(
            checked = checked,
            onCheckedChange = {
                checked = it
                model.setToggle(operation, it)
            },
        )
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    Card(
        shape = MaterialTheme.shapes.small,
        colors = CardDefaults.cardColors(containerColor = Color.White),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            HorizontalDivider(Modifier.padding(vertical = 10.dp))
            content()
        }
    }
}

@Composable
private fun StatusRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            label,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(end = 12.dp),
        )
        Text(
            value,
            fontWeight = FontWeight.Medium,
            textAlign = TextAlign.End,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun KeepAlivePrompt(title: String, detail: String, action: String, onClick: () -> Unit) {
    Surface(
        color = MaterialTheme.colorScheme.errorContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.SemiBold)
                Text(detail, style = MaterialTheme.typography.bodySmall)
            }
            Button(onClick = onClick) { Text(action) }
        }
    }
}

@Composable
private fun StatusBanner(text: String, background: Color, icon: androidx.compose.ui.graphics.vector.ImageVector) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = background)
        Text(text)
    }
}

@Composable
private fun CloudCtlTheme(content: @Composable () -> Unit) {
    val colors = androidx.compose.material3.lightColorScheme(
        primary = Color(0xFF176B53),
        secondary = Color(0xFF315B74),
        tertiary = Color(0xFF80551F),
        background = Color(0xFFF7F9F8),
        surface = Color(0xFFF7F9F8),
        error = Color(0xFFBA1A1A),
    )
    MaterialTheme(colorScheme = colors, content = content)
}

private fun ServiceState.label(): String = name

private fun AuthorizedTaskState.label(): String = when (this) {
    AuthorizedTaskState.Queued -> "排队中"
    AuthorizedTaskState.Running -> "运行中"
    AuthorizedTaskState.WaitingConfirmation -> "等待确认"
    AuthorizedTaskState.Stopping -> "停止中"
    AuthorizedTaskState.Succeeded -> "已完成"
    AuthorizedTaskState.Failed -> "失败"
    AuthorizedTaskState.Canceled -> "已取消"
    AuthorizedTaskState.Unknown -> "未知"
}

private fun ArtifactKind.label(): String = when (this) {
    ArtifactKind.Apk -> "APK"
    ArtifactKind.ApkSplit -> "Split APK"
    ArtifactKind.Media -> "Media"
    ArtifactKind.AutomationPackage -> "Automation package"
    ArtifactKind.Unknown -> "Artifact"
}

private fun ArtifactDeliveryState.label(): String = when (this) {
    ArtifactDeliveryState.Queued -> "排队中"
    ArtifactDeliveryState.Downloading -> "下载中"
    ArtifactDeliveryState.Verified -> "已校验"
    ArtifactDeliveryState.Delivered -> "已交付"
    ArtifactDeliveryState.Failed -> "失败"
    ArtifactDeliveryState.Unknown -> "未知"
}

private fun ConfirmationRiskLevel.label(): String = name

private fun String.userLabel(): String = when (this) {
    "PLACEHOLDER" -> "待接入"
    else -> this
}

private fun formatBytes(value: Long): String = when {
    value >= 1_073_741_824L -> "%.1f GB".format(value / 1_073_741_824.0)
    value >= 1_048_576L -> "%.1f MB".format(value / 1_048_576.0)
    else -> "$value B"
}
