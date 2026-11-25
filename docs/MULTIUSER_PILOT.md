# Collaudo con due identita temporanee

25 novembre 2026. Prova SQL/HTTP sul server riuscita, con output dell'operatore
ok=true. TXT e PDF con inferenza avevano gia superato il precedente collaudo.
Evidenza: docs/validation/2026-11-25-multiuser-pilot.json.

## Esito verificato sul pilota

Due account temporanei sono stati autenticati sull'API reale. Accessi incrociati
bloccati in entrambe le direzioni, analisi memorizzate separate anche con hash
identici, grant viewer con lettura consentita e scrittura negata, revoca efficace
sulla sessione ancora valida: tutti i controlli sono passati. Nessuna inferenza
nuova richiesta: questa prova usa risultati sintetici deterministici nella cache.

Documenti sintetici rimossi dall'applicazione; logout, revoca delle sessioni e
disattivazione dei due account verificati. Identita, nuclei e audit rimangono per
tracciabilita; manifest conservato nel tmpfs del container. Gli account personali
esistenti non sono stati usati o modificati dal test. Nessun rilascio di produzione.

## Ambito

Eseguire scripts/smoke_isolation.py nel container jarvis-backend-ai-pilot sulla VM
jarvis, con scripts/smoke_analysis.py nella stessa directory. Nessuna nuova
immagine, migrazione, porta pubblicata o modifica ai profili Ultron necessaria.

L'API non offre ancora provisioning di nuovi account. Il solo helper di collaudo
crea quindi due utenti, due nuclei, due appartenenze owner e due persone tramite
transazione PostgreSQL. Gli ID sono UUID nuovi; email nel dominio .invalid, nomi
marcati dal run ID e password casuali in memoria. L'inserimento non aggiorna
account esistenti e fallisce se incontra collisioni. Il database e l'identita
configurata vengono controllati prima dell'inserimento.

I login, upload, letture, operazioni vietate, cache, logout e verifiche di revoca
usano l'API HTTP reale del pilota, su loopback. I due documenti hanno identici
byte/hash ma ID e proprieta distinti. Per verificare l'isolamento delle analisi
senza altre inferenze, l'helper inserisce due risultati deterministici marcati
isolation-fixture nei soli nuovi documenti, dopo verifica di proprieta e hash.
Non e una prova di qualita AI o di due identita personali reali gia esistenti.

## Verifiche eseguite

- Ogni login corrisponde al proprio nuovo account.
- Ogni account legge originale e analisi del proprio documento; POST analysis
  restituisce il risultato gia presente con ID corretto.
- L'altro account riceve 404 su originale, analisi, richiesta di analisi e
  cancellazione, in entrambe le direzioni.
- Un grant viewer temporaneo a B sul nucleo A consente originale/analisi, ma
  POST analysis e DELETE rimangono vietati con 403.
- La rimozione del grant viewer blocca subito le stesse letture con 404,
  conservando la validita della sessione B su GET /me.
- I due documenti sintetici vengono rimossi solo dopo verifica dei loro byte
  tramite i rispettivi owner; GET successivo deve restituire 404.
- Logout e revoca sono verificati per entrambe le sessioni.

Grant e revoca della membership sono predisposti via SQL solo fra questi nuovi
ID: non e stato introdotto un endpoint amministrativo pubblico per farlo.

## Pulizia e ripristino

Il finally disattiva soltanto i due account del test e revoca tutte le loro
sessioni. Prima degli UPDATE blocca e verifica ID, email, nuclei, nomi e owner
attesi; identita discordanti impediscono la mutazione. Non esegue TRUNCATE,
cancellazioni generali, rimozioni di account o modifiche degli eventi di audit.
Le righe delle identita/nuclei e l'audit restano per tracciabilita. In caso di
fallimento i documenti sintetici non ancora rimossi rimangono per diagnosi.

Un manifest locale nel tmpfs del container contiene solo ID, nomi sintetici e
stato, con modo 0600; mai password, token o hash delle password. Il percorso e il
run ID sono stampati nel risultato. Il manifest puo scomparire fermando questo
container temporaneo: conservare il JSON finale, senza incollare credenziali.

Se il processo viene interrotto prima del finally, lo stesso helper supporta
--deactivate-run RUN_ID. Questa modalita non ripete il test e non crea utenti:
identifica solo le due email .invalid e i due nuclei del run, ne verifica il
collegamento, poi disattiva gli account e revoca le sessioni. Non cancella dati.
Va eseguita sulla VM jarvis, nel medesimo container o altro container interno
configurato con lo stesso database; usare il percorso dello script scaricato.

## Prove locali e limiti

Undici casi simulati verificano successo, lettura incrociata erroneamente
consentita, cache condivisa per hash, viewer con scrittura, revoca non applicata,
contenuto diverso prima della pulizia, rifiuto di identita discordanti,
disattivazione dopo timeout e modalita di recupero. Non sostituiscono il collaudo
SQL/HTTP sul server, ora anch'esso superato come riportato sopra. La suite mirata complessiva restituisce 98 passed; lint e
formattazione verificati. Il precedente risultato Linux resta 92 passed / 1
skipped sul codice applicativo dell'immagine: non e un risultato Linux di questo
nuovo helper.

Questo collaudo non prova isolamento delle copie conservate dall'account tecnico
Open WebUI, sostituzione di documenti, invalidazione dell'analisi, ricerca su
archivi, strumenti PDF visivi o purge fisico delle versioni S3. Questi limiti
restano espliciti dopo il successo del test di autorizzazione.
