from pathlib import Path
import logging

from netra.config import load_config
from netra.core.conversation_agent import ConversationAgent
from netra.core.intent_parser import IntentParser
from netra.hardware.stub_adapter import StubHardwareAdapter
from netra.models.types import SessionState
from netra.services.braille_service import BrailleService
from netra.services.document_service import DocumentService
from netra.services.ocr_service import OCRService
from netra.services.ollama_service import OllamaService
from netra.services.store_service import StoreService
from netra.services.stt_service import STTService
from netra.services.tts_service import TTSService
from netra.utils.logging_utils import configure_logging


def run() -> None:
    root = Path(__file__).resolve().parents[2]
    config = load_config(root / "config.json")
    log_path = configure_logging(root / config.logs_dir, config.log_level)
    logger = logging.getLogger(__name__)
    logger.info("NETRA startup initiated")
    logger.info("Using config: docs_dir=%s, model=%s", config.docs_dir, config.ollama_model)
    logger.info("Logs are written to %s", log_path)

    hardware = StubHardwareAdapter()
    ocr = OCRService()
    docs = DocumentService(config.docs_dir, ocr)
    ollama = OllamaService(config.ollama_host, config.ollama_port, config.ollama_model)
    braille = BrailleService(config.braille_table, config.braille_cells)
    tts = TTSService(config.piper_model)
    stt = STTService(
        config.whisper_model,
        config.audio_sample_rate,
        config.wake_word,
        use_live_mic=config.stt_use_live_mic,
        allow_typed_fallback=config.stt_allow_typed_fallback,
    )
    store = StoreService(str(root / config.db_path))

    documents = docs.scan_documents()
    state = SessionState()

    agent = ConversationAgent(
        state=state,
        documents=documents,
        document_service=docs,
        ollama=ollama,
        braille=braille,
        tts=tts,
        store=store,
        hardware=hardware,
        braille_output_file=str(root / config.braille_output_file),
    )

    parser = IntentParser(ollama)

    tts.speak("NETRA is ready. You can speak naturally at any time.", hardware)

    if documents:
        first = ", ".join(doc.name for doc in documents[:5])
        tts.speak(f"I found {len(documents)} documents. First files are {first}", hardware)
        logger.info("Discovered %d documents", len(documents))
    else:
        tts.speak("No documents found in configured docs directory.", hardware)
        logger.warning("No documents found in %s", config.docs_dir)

    while state.running:
        documents = docs.scan_documents()
        agent.documents = documents

        if config.enable_wake_word:
            stt.wait_for_wake(hardware, 3)

        command = stt.listen_for_command(hardware, config.record_seconds)
        if not command.strip():
            tts.speak("I did not catch that. Please repeat.", hardware)
            continue
        logger.info("User command text: %s", command)
        intent = parser.parse(command, [doc.name for doc in documents])
        logger.info("Resolved intent: %s value=%s", intent.action, intent.value)
        agent.handle_intent(intent)


if __name__ == "__main__":
    run()
