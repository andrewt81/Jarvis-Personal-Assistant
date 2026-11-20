# Applicazione Jarvis e inferenza su Ultron

20 novembre 2026. Implementazione candidata pubblicata in PR #11; nessun deployment
o collaudo applicativo remoto effettuato. Verifica HTTP di rete riuscita come riportato sotto.

## Ruoli confermati dall'utente e dagli output della sessione

| Elemento | Ruolo e stato |
|---|---|
| `ultron` | Inferenza: Ollama, Open WebUI e Docling; i tre container risultano healthy nell'output fornito. |
| Profilo `jarvis` | Profilo Open WebUI su Ultron. L'handoff attesta ragionamento booleano true, contesto 65536 e strumenti PDF/calcolo/pianificazione. Non è stato riconfermato via API in questa sessione. |
| Host `jarvis` | Applicazione: Debian 13.7, circa 8 GiB RAM, solo Traefik attivo e healthy, rete Docker proxy, directory /opt/jarvis già presente. Il suo contenuto non è stato ancora acquisito. |
| `edith` | PostgreSQL 17 e RustFS per i dati dell'applicazione, come previsto dalla documentazione originale e riconfermato dall'utente. Database jarvis, ruolo jarvis_app e bucket jarvis-documents-prod dedicati, da verificare. |

L'utente ha confermato di attenersi all'architettura originale: applicazione su
Jarvis, PostgreSQL e documenti S3 su Edith, inferenza su Ultron. La precedente
esclusione di Edith in questo documento era un'interpretazione errata ed e ritirata.
I file predisposti su Jarvis puntano a 10.10.30.20:5432, database jarvis, ruolo
jarvis_app, SSL require, e http://10.10.30.20:9000, bucket jarvis-documents-prod,
regione us-east-1, path-style true. Questo conferma la configurazione prevista;
esistenza, contenuto e permessi delle risorse non sono ancora verificati.
Non sono previsti spostamenti dei dati, nuovi database o nuovi bucket in questo
incremento. Non toccare risorse appartenenti ad altre applicazioni su Edith.
Il traffico applicazione-inferenza Jarvis-Ultron usa Tailscale; Jarvis-Edith mantiene
gli endpoint della rete interna gia predisposti, da collaudare. Ultron non necessita
di accesso diretto a database o bucket per il flusso dell'adattatore.

## Implementazione

### Verifiche successive sulla rete e sui template dell'host

Output forniti dall'utente: Tailscale e ora presente sull'host applicativo jarvis,
con indirizzo **100.79.96.2**. La richiesta a http://100.127.56.71:3000/health ha
restituito HTTP 200 dall'host e `{"status":true}` dal container Traefik sulla rete
proxy. Questo verifica la raggiungibilita HTTP da quei due contesti, non ancora
l'autenticazione API o il funzionamento del futuro container backend.

Sono presenti config/postgresql.env, secrets/postgresql-password, secrets/rustfs.env,
deploy/backend.env.template e deploy/compose.backend.template.yaml sotto /opt/jarvis.
Sono stati acquisiti i nomi delle variabili e i parametri non segreti: endpoint
PostgreSQL/S3 su Edith, database jarvis e bucket jarvis-documents-prod. Proprieta,
autenticazione e permessi restano da verificare.
Il codice supporta i nomi presenti nei template senza richiedere la riscrittura dei
file sul server:

| Nome predisposto sull'host | Campo di configurazione |
|---|---|
| JARVIS_DB_HOST / JARVIS_DB_PORT | postgres_host / postgres_port |
| JARVIS_DB_NAME / JARVIS_DB_USER | postgres_database / postgres_user |
| JARVIS_DB_SSLMODE / JARVIS_DB_PASSWORD_FILE | postgres_sslmode / postgres_password_file |
| JARVIS_S3_ENDPOINT | s3_endpoint_url |
| JARVIS_S3_ACCESS_KEY / JARVIS_S3_SECRET_KEY | s3_access_key_id / s3_secret_access_key |

I nomi canonici JARVIS_POSTGRES_* e JARVIS_S3_* piu specifici restano prioritari
quando valorizzati; un valore vuoto lascia usare l'alias. Nessun segreto e stato
letto dall'host, copiato nel repository o incluso nell'output diagnostico.

### Flusso del provider

Il DocumentService continua ad autorizzare account/nucleo/ruolo prima di recuperare
l'originale e invocare il provider. L'API e il client Android conservano i contratti
esistenti. Il provider `openwebui` aggiunge questo flusso:

1. Validazione dell'endpoint configurato: IP IPv4 Tailscale esplicito, HTTP o HTTPS;
   niente redirect, proxy d'ambiente, URL di file o endpoint pubblici.
2. Lettura del profilo, senza aggiornarlo. Sono richiesti think booleano true e
   jarvis_original_pdf; sono ammessi soltanto i tre strumenti personalizzati già noti.
   Knowledge base e filtri associati al profilo sono esclusi dal pilota.
3. Upload del solo originale richiesto (massimo 25 MiB) con nome generico e attesa
   dell'estrazione. L'upload segue il flusso del client PowerShell già usato; il
   comportamento di immagini, testo e PDF va confermato sull'installazione effettiva.
4. Nuova conversazione con un unico documento e senza cronologia precedente. Native
   tool calling attivo; memoria, ricerca web, generazione immagini e code interpreter
   disattivati nella richiesta. Parametri di generazione e system prompt del profilo
   non vengono modificati.
5. Risposta accettata soltanto quando message.done è booleano true e task_ids è un
   array vuoto. Modifica esterna della conversazione, errori, timeout o stato non
   valido producono indisponibilità, senza fallback cloud e senza risposta parziale.
6. Validazione stretta del solo JSON finale. Non si estraggono JSON da ragionamenti,
   blocchi Markdown o risultati degli strumenti. I valori restano fatti dichiarati dal
   modello con source_text: lo schema non certifica la verità delle citazioni.

Il risultato riporta provider=openwebui e il nome del profilo. L'analisi persistita
mantiene l'hash SHA-256 dell'originale tramite il servizio esistente. La versione del
profilo/modello base non è ancora registrata nel database dell'applicazione.

## Credenziali e configurazione

L'account Open WebUI deve essere dedicato all'applicazione, non amministratore, senza
altri documenti o conversazioni personali e con accesso al profilo necessario.
La separazione dei nuclei rimane nel backend applicativo; questo account tecnico non
costituisce un'identità Open WebUI distinta per ogni familiare. Non concedere agli utenti
dell'applicazione l'accesso diretto all'account tecnico. Il controllo del ruolo reale
dell'account e dei permessi deve far parte del collaudo prima dell'attivazione.

Non trasferire la chiave personale DPAPI del PC. Il segreto applicativo va predisposto
separatamente come file leggibile dall'UID/GID del container e montato in sola lettura.
Gli esempi contengono soltanto percorsi, mai valori di chiavi.

| Variabile | Valore candidato |
|---|---|
| JARVIS_AI_PROVIDER | openwebui |
| JARVIS_OPENWEBUI_BASE_URL | http://100.127.56.71:3000, HTTP verificato da Jarvis e Traefik; autenticazione API da provare |
| JARVIS_OPENWEBUI_MODEL | jarvis |
| JARVIS_OPENWEBUI_TIMEOUT_SECONDS | 3600, timeout complessivo tra 1 e 7200 secondi |
| JARVIS_AI_API_KEY_HOST_FILE | /opt/jarvis/secrets/openwebui-api-key, da predisporre |
| JARVIS_POSTGRES_ENV_FILE | /opt/jarvis/config/postgresql.env, parametri non segreti verificati |
| JARVIS_S3_ENV_FILE | /opt/jarvis/secrets/rustfs.env, segreti gia predisposti e non letti nella chat |

Nel Compose il segreto selezionato è montato in /run/secrets/ai_api_key, usato dal
provider esplicitamente scelto. Il percorso host diventa obbligatorio. Il provider di
default del Compose è disabled: un valore mancante non attiva OpenAI. L'operatore può
ancora scegliere openai in modo esplicito con il relativo segreto.

## Limiti e gate prima dell'uso reale

- Il codice usa gli endpoint osservati nel precedente client. I test simulano quel
  protocollo: non provano compatibilità live, capacità del modello o raggiungibilità.
- Il primo pilota deve usare soltanto documenti sintetici e un unico nucleo di prova.
  Non caricare documenti personali prima dei controlli di identità e conservazione.
- File e chat sono salvati anche in Open WebUI. L'adattatore non li elimina e non cancella
  originali. I log applicativi registrano soltanto gli ID tecnici delle nuove risorse;
  non contengono prompt, nomi originali, chiavi o ragionamento. Open WebUI può conservare
  ragionamento e strumenti nella sua cronologia: non sono copiati nel risultato applicativo.
- Timeout o interruzioni possono lasciare un job remoto ancora attivo e risorse residue.
  Una richiesta fallita non viene ritentata automaticamente. La cancellazione di un
  documento nell'applicazione non elimina queste copie remote: sincronizzazione del
  ciclo di vita e retention sono un requisito prima dell'uso con dati personali.
- L'endpoint di analisi dell'MVP rimane sincrono. Operazioni lunghe possono superare i
  timeout di Traefik/client Android; non sono stati modificati proxy o client né aggiunta
  una coda persistente. Il test iniziale deve essere breve. Un job applicativo asincrono
  e riprendibile è necessario prima dei documenti lunghi.
- La cache analisi esistente è indicizzata sull'hash del documento. Un cambio provider o
  profilo non forza una nuova analisi di un originale già analizzato. Usare un nuovo
  documento sintetico nel pilota; l'invalidazione per versione del provider è successiva.
- Il codice di Open WebUI e degli strumenti installati resta parte del perimetro fidato:
  una allowlist di ID non verifica l'hash del codice degli strumenti né i filtri globali.

## Collaudo remoto ancora da eseguire

1. Verificare il contenuto non sensibile di /opt/jarvis e preservare configurazioni esistenti.
2. HTTP da jarvis e Traefik a Ultron verificato; resta la prova dal container applicativo.
   Non pubblicare ulteriori porte di Ollama o Docling e non aprire endpoint AI su Internet.
3. Verificare su Edith database jarvis e bucket jarvis-documents-prod usando le sole
   credenziali dedicate gia predisposte. Controlli iniziali di sola lettura: identita
   del database, TLS effettivo, privilegi del ruolo e HEAD del bucket; niente migrazioni,
   scritture di oggetti o modifiche a ruoli prima del riscontro sullo stato reale.
4. Predisporre l'identità tecnica e provarne il rifiuto di accesso a documenti estranei.
5. Verificare lettura del profilo e strumenti autorizzati senza modifiche remote.
6. Analizzare un piccolo PDF sintetico tramite API applicativa: confrontare hash originale,
   fatti, pagina fisica, citazioni, versione e consultazione visiva se necessaria.
7. Ripetere con identità anonima, viewer, altro nucleo e ID documento estraneo: nessun
   upload/invocazione su Ultron deve partire nei casi non autorizzati.
8. Provare timeout, estrazione fallita, chiave revocata, JSON malformato e risposta non
   completa. Nessuna analisi deve essere persistita come riuscita.
9. Chiudere conservazione/cancellazione delle copie remote e gestione dei job lunghi prima
   dell'uso con dati personali. Non trattare la sola suite locale come via libera al rilascio.

## Verifiche locali del 20 novembre

### Riscontri dal container su Jarvis

Output dell'utente sul commit 911688036092399e77f1d1ff1577ee17bcae3de4:
build Linux del Dockerfile backend completata e immagine locale
jarvis-backend:preflight-9116880 creata. Il comando jarvis.preflight, eseguito come
utente del container sulla rete proxy con il solo segreto PostgreSQL montato in
lettura e i due env file esistenti, ha restituito ok=true. Identita database/ruolo
confermata, TLS attivo, USAGE e CREATE su public disponibili, migrazioni assenti.
HEAD sul bucket S3 riuscito; lettura/scrittura di oggetti non provate. Nessuna
migrazione, creazione del proprietario applicativo o avvio del backend effettuati.

La suite completa puo ora essere eseguita nell'immagine Linux tramite
scripts/validate_image.py --commit SHA, in un container temporaneo senza env file,
segreti, porte o volumi host. Lo script scarica l'archivio GitHub del commit indicato,
verifica che tutti i file Python installati dell'applicazione coincidano con esso,
crea un virtualenv temporaneo con le dipendenze runtime dell'immagine e installa
pytest 8.4.2, httpx 0.28.1 e Ruff 0.17.1. Esegue lint, formattazione, compilazione e
pytest. Scaricamenti e risultati risiedono soltanto nel filesystem temporaneo del
container. Il controllo non fornisce credenziali di produzione ai test e non esegue
migrazioni. Il risultato completo resta da acquisire; non dedurlo dal preflight.

### Cronologia delle verifiche locali precedenti

- Verifica su Edith tramite output dell'utente: database jarvis di proprieta di
  jarvis_app; ruolo con LOGIN e senza SUPERUSER, CREATEDB o CREATEROLE. Nessuna
  tabella applicativa elencata e public.alembic_version assente. Nessuna migrazione
  applicata in questa sessione.
- Aggiunto `python -m jarvis.preflight`, da eseguire nell'immagine applicativa con
  i file protetti gia presenti su Jarvis. La connessione PostgreSQL usa una transazione
  READ ONLY e verifica database, ruolo e TLS effettivo tramite pg_stat_ssl. Riporta
  privilegi USAGE/CREATE su public e presenza della tabella migrazioni senza modificarli.
  Il controllo S3 usa esclusivamente HEAD del bucket: non prova lettura o scrittura
  di oggetti. L'output JSON non contiene DSN, chiavi, password o corpi degli errori.
- **63 test locali superati**: preflight, configurazione e connettore, con engine e
  servizio S3 simulati. I driver effettivi e le credenziali reali vanno collaudati
  nel container Linux; l'ambiente locale blocca anche un'estensione DLL di SQLAlchemy.
  I test del preflight usano dipendenze simulate e non certificano la connettivita.
- Ruff check, formattazione (73 file), compilazione Python e diff check superati
  dopo l'aggiunta del preflight. Build e suite completa restano da eseguire su Linux.

- Aggiornamento compatibilita template host: **55 test superati** (connettore e
  configurazione), inclusi i dieci nuovi casi per alias, precedenza dei parametri,
  fallback su valori vuoti e mancata esposizione dei segreti sintetici nel repr.

- **45 test superati**: suite del nuovo connettore e configurazione. Il trasporto e il
  server Open WebUI sono simulati. Sono inclusi divieto di upload prima del controllo
  applicativo per nucleo assente/viewer/documento inesistente, chat separate, attesa di
  done e task_ids, errori e JSON invalidi, endpoint estranei, redirect, proxy, credenziali
  mancanti, timeout e verifica del wrapper asincrono tramite esecutore inline simulato.
- Ruff check su tutto il repository: superato. Ruff format --check: 71 file conformi.
- Compilazione Python di backend/src: superata. git diff --check: superato.
- docker compose config --quiet del Compose di produzione: superato con file di
  configurazione e segreto sintetici locali, senza contattare i servizi reali.
- Suite completa preesistente: **non completata**. L'avvio dei test basati su asyncio.run
  si blocca prima del codice applicativo, in socket._fallback_socketpair durante la
  creazione del loop Proactor di Windows. Le esecuzioni bloccate sono state interrotte;
  il problema non viene aggirato modificando il runtime applicativo o i test precedenti.
- Build Docker: **bloccata**, accesso negato a ~/.docker/buildx/.lock in questo ambiente.
- Nessun test live, migrazione, caricamento di documenti reali, modifica del profilo,
  merge o deployment. Il candidato viene pubblicato su ramo dedicato con PR in bozza
  verso develop. Prima del rilascio servono suite completa e build nel
  contesto Linux previsto, oltre al collaudo di rete e identita descritto sopra.

## Ripristino

Nessun rollback remoto necessario: questo incremento non è stato distribuito. Conservare
immagine e configurazione precedenti prima del futuro pilota. Per disabilitare l'analisi,
impostare JARVIS_AI_PROVIDER=disabled e ricreare il solo backend con la configurazione
verificata. Non riabilitare il cloud automaticamente. Il ripristino del backend non revoca
la chiave tecnica e non rimuove le copie su Open WebUI: gestirle separatamente secondo la
politica concordata. Nessuna modifica a Ultron, Traefik, Edith, storage o originali è inclusa.
