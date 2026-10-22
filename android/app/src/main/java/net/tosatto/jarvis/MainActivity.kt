package net.tosatto.jarvis

import android.os.Bundle
import android.provider.OpenableColumns
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(Modifier.fillMaxSize()) { JarvisApp() }
            }
        }
    }
}

@Composable
private fun JarvisApp() {
    val context = LocalContext.current
    val store = remember { SecureSessionStore(context) }
    val client = remember { JarvisClient(store) }
    var signedIn by remember { mutableStateOf(store.load() != null) }
    if (!signedIn) {
        Login(client) { signedIn = true }
    } else {
        Today(client) { store.clear(); signedIn = false }
    }
}

@Composable
private fun Login(client: JarvisClient, onSuccess: () -> Unit) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.Center) {
        Text("Jarvis", style = MaterialTheme.typography.displaySmall)
        Text("La tua segretaria personale")
        Spacer(Modifier.height(24.dp))
        OutlinedTextField(email, { email = it }, label = { Text("Email") }, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(password, { password = it }, label = { Text("Password") }, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(enabled = !busy, onClick = {
            busy = true
            scope.launch {
                runCatching { client.login(email, password) }
                    .onSuccess { onSuccess() }
                    .onFailure { error = it.message }
                busy = false
            }
        }) { Text(if (busy) "Accesso…" else "Accedi") }
    }
}

@Composable
private fun Today(client: JarvisClient, onLogout: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var household by remember { mutableStateOf<Household?>(null) }
    var tasks by remember { mutableStateOf<List<JarvisTask>>(emptyList()) }
    var message by remember { mutableStateOf("Caricamento…") }
    var newTaskTitle by remember { mutableStateOf("") }
    var creatingTask by remember { mutableStateOf(false) }
    var analysis by remember { mutableStateOf<JarvisAnalysis?>(null) }
    var acceptingActions by remember { mutableStateOf(false) }

    fun refresh() = scope.launch {
        runCatching {
            val selected = client.households().firstOrNull() ?: error("Nessun nucleo disponibile")
            household = selected
            tasks = client.tasks(selected.id)
        }.onSuccess { message = if (tasks.isEmpty()) "Nessuna attività aperta" else "" }
            .onFailure { message = it.message ?: "Errore" }
    }
    androidx.compose.runtime.LaunchedEffect(Unit) { refresh() }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null && household != null) scope.launch {
            runCatching {
                val metadata = context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                    cursor.moveToFirst()
                    val name = cursor.getString(cursor.getColumnIndexOrThrow(OpenableColumns.DISPLAY_NAME))
                    val size = cursor.getLong(cursor.getColumnIndexOrThrow(OpenableColumns.SIZE))
                    name to size
                } ?: ("documento" to 0L)
                require(metadata.second in 1..(25L * 1024 * 1024)) { "Il documento supera il limite di 25 MiB" }
                val bytes = context.contentResolver.openInputStream(uri)!!.use { it.readBytes() }
                val documentId = client.upload(household!!.id, metadata.first, context.contentResolver.getType(uri) ?: "application/pdf", bytes)
                client.analyze(household!!.id, documentId)
            }.onSuccess {
                analysis = it
                message = "Documento analizzato: verifica sempre i dati proposti"
            }
                .onFailure { message = it.message ?: "Caricamento non riuscito" }
        }
    }

    Column(Modifier.padding(20.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column { Text("Oggi", style = MaterialTheme.typography.headlineLarge); Text(household?.name.orEmpty()) }
            Button(onClick = onLogout) { Text("Esci") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { picker.launch(arrayOf("application/pdf", "image/*", "text/plain")) }) { Text("Carica e analizza") }
            Button(onClick = { refresh() }) { Text("Aggiorna") }
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedTextField(
                newTaskTitle,
                { newTaskTitle = it },
                label = { Text("Nuova attività") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            Button(
                enabled = newTaskTitle.isNotBlank() && !creatingTask && household != null,
                onClick = {
                    creatingTask = true
                    scope.launch {
                        runCatching { client.createTask(household!!.id, newTaskTitle) }
                            .onSuccess {
                                newTaskTitle = ""
                                message = "Attività aggiunta"
                                refresh()
                            }
                            .onFailure { message = it.message ?: "Creazione non riuscita" }
                        creatingTask = false
                    }
                },
            ) { Text(if (creatingTask) "Aggiungo…" else "Aggiungi") }
        }
        if (message.isNotBlank()) Text(message, modifier = Modifier.padding(vertical = 16.dp))
        analysis?.let { value ->
            Card(Modifier.fillMaxWidth().padding(bottom = 12.dp)) {
                Column(Modifier.padding(16.dp)) {
                    Text(value.documentType, style = MaterialTheme.typography.titleMedium)
                    Text(value.summary, modifier = Modifier.padding(vertical = 8.dp))
                    value.deadlines.forEach { Text("Scadenza: $it") }
                    value.suggestedActions.forEach { Text("• $it") }
                    if (value.missingInformation.isNotEmpty()) {
                        Text("Da verificare: ${value.missingInformation.joinToString()}")
                    }
                    Button(
                        enabled = value.suggestedActions.isNotEmpty() && !acceptingActions,
                        onClick = {
                            acceptingActions = true
                            scope.launch {
                                val remaining = value.suggestedActions.toMutableList()
                                runCatching {
                                    value.suggestedActions.forEach {
                                        client.createTask(household!!.id, it)
                                        remaining.remove(it)
                                        analysis = value.copy(suggestedActions = remaining.toList())
                                    }
                                }.onSuccess {
                                    analysis = null
                                    message = "Azioni aggiunte a Oggi"
                                }.onFailure { message = it.message ?: "Creazione non riuscita" }
                                refresh()
                                acceptingActions = false
                            }
                        },
                    ) { Text(if (acceptingActions) "Aggiungo…" else "Aggiungi azioni a Oggi") }
                }
            }
        }
        LazyColumn(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(tasks, key = { it.id }) { task ->
                Card(Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column(Modifier.weight(1f)) { Text(task.title); Text(task.priority.uppercase()) }
                        Button(onClick = {
                            scope.launch {
                                runCatching { client.complete(household!!.id, task) }
                                    .onSuccess { refresh() }
                                    .onFailure { message = it.message ?: "Aggiornamento non riuscito" }
                            }
                        }) { Text("Fatto") }
                    }
                }
            }
        }
    }
}
