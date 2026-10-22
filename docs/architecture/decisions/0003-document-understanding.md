# ADR 0003: comprensione documentale strutturata e conferma umana

## Stato

Accettata per l'MVP v0.1.

## Decisione

Il primo flusso intelligente usa un'interfaccia applicativa indipendente dal fornitore. La prima
implementazione chiama la Responses API di OpenAI con output vincolato da JSON Schema e modello
configurabile, inizialmente `gpt-6-luna` con reasoning `low` e dettaglio PDF `low`.

La chiave API viene letta soltanto da un file montato in sola lettura. Le richieste impostano
`store: false`. L'originale resta in RustFS; PostgreSQL conserva una versione dell'analisi con hash
della fonte, modello, riassunto, fatti e scadenze corredati dal testo sorgente, azioni suggerite e
informazioni mancanti.

L'analisi non crea attività né esegue azioni esterne. L'utente deve confermare nell'app quali
suggerimenti aggiungere a Oggi. Errori o indisponibilità del fornitore non alterano l'originale.

## Conseguenze

- I documenti selezionati con “Carica e analizza” vengono inviati al fornitore AI configurato.
- Il costo è a consumo e il modello può essere sostituito tramite configurazione.
- Il contratto strutturato limita errori di formato ma non garantisce la correttezza semantica;
  l'interfaccia ricorda quindi all'utente di verificare fatti, scadenze e suggerimenti.
- Un futuro fornitore locale o esterno potrà implementare la stessa interfaccia senza modificare
  API, storage o modello multiutente.
