from pathlib import Path
import logging
import platform

from netra.config import load_config
from netra.core.conversation_agent import ConversationAgent
from netra.core.intent_parser import IntentParser
from netra.models.types import SessionState
from netra.services.braille_service import BrailleService
from netra.services.document_service import DocumentService
from netra.services.ocr_service import OCRService
from netra.services.llama_service import LlamaCppService
from netra.services.store_service import StoreService
from netra.services.stt_service import STTService
from netra.services.tts_service import TTSService
from netra.utils.logging_utils import configure_logging


def _create_hardware_adapter(config):
    """
    Create appropriate hardware adapter based on config and platform.
    
    Modes:
    - "auto": Detect platform automatically (RPi on ARM Linux, Stub otherwise)
    - "rpi": Force Raspberry Pi adapter
    - "stub": Force stub adapter (for development/testing)
    """
    logger = logging.getLogger(__name__)
    mode = config.hardware_mode.lower()
    
    # Auto-detect: Check if running on Raspberry Pi
    is_raspberry_pi = False
    if mode == "auto":
        try:
            # Check for Raspberry Pi by looking at /proc/cpuinfo or platform
            if platform.machine().startswith('aarch64') or platform.machine().startswith('arm'):
                # Additional check for Pi-specific files
                if Path("/proc/device-tree/model").exists():
                    model = Path("/proc/device-tree/model").read_text()
                    is_raspberry_pi = "Raspberry Pi" in model
                    logger.info("Detected hardware: %s", model.strip())
        except Exception:
            pass
    
    # Use RPi adapter if forced or auto-detected
    if mode == "rpi" or (mode == "auto" and is_raspberry_pi):
        try:
            from netra.hardware.rpi_adapter import RaspberryPiHardwareAdapter
            logger.info("Using Raspberry Pi hardware adapter")
            return RaspberryPiHardwareAdapter(audio_device=config.rpi_audio_device)
        except ImportError as exc:
            logger.warning("RPi adapter import failed: %s, falling back to stub", exc)
    
    # Fallback to stub adapter
    from netra.hardware.stub_adapter import StubHardwareAdapter
    logger.info("Using stub hardware adapter")
    return StubHardwareAdapter()


def run() -> None:
    root = Path(__file__).resolve().parents[2]
    config = load_config(root / "config.json")
    log_path = configure_logging(root / config.logs_dir, config.log_level)
    logger = logging.getLogger(__name__)
    logger.info("NETRA startup initiated")
    logger.info("Using config: docs_dir=%s, model=%s", config.docs_dir, config.llama_model_path)
    logger.info("Logs are written to %s", log_path)

    # Create hardware adapter (auto-detect RPi or use stub)
    hardware = _create_hardware_adapter(config)
    
    ocr = OCRService()
    docs = DocumentService(config.docs_dir, ocr)
    llama = LlamaCppService(
        str(root / config.llama_model_path),
        n_threads=config.llama_threads,
        n_ctx=config.llama_context_size,
        temperature=config.llama_temperature
    )
    braille = BrailleService(config.braille_table, config.braille_cells)
    tts = TTSService(config.piper_model)
    stt = STTService(
        config.whisper_model,
        config.vosk_model,
        config.audio_sample_rate,
        config.wake_word,
        stt_engine=config.stt_engine,
        stt_engine_wake_word=config.stt_engine_wake_word,
        stt_engine_command=config.stt_engine_command,
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
        llama=llama,
        braille=braille,
        tts=tts,
        store=store,
        hardware=hardware,
        braille_output_file=str(root / config.braille_output_file),
        ocr_lines_per_chunk=config.ocr_lines_per_chunk,
        pdf_pages_per_chunk=config.pdf_pages_per_chunk,
        braille_display_delay=config.braille_display_delay,
    )

    parser = IntentParser(llama)

    logger.info("NETRA services initialized")
    tts.speak("NETRA is ready. You can speak naturally at any time.", hardware)

    if documents:
        first = ", ".join(Path(doc.name).stem.replace("_", " ") for doc in documents[:5])
        tts.speak(f"I found {len(documents)} documents. The first items are {first}", hardware)
        logger.info("Discovered %d documents", len(documents))
    else:
        tts.speak("I could not find any documents in your folder.", hardware)
        logger.warning("No documents found in %s", config.docs_dir)

    tts.speak("What would you like me to do?", hardware)

    try:
        while state.running:
            documents = docs.scan_documents()
            agent.documents = documents

            if config.enable_wake_word:
                stt.wait_for_wake(hardware, 3)

            command = stt.listen_for_command(hardware, config.record_seconds)
            if not command.strip():
                tts.speak("I did not catch that. Please say it again.", hardware)
                continue
            
            logger.info("User command text: %s", command)
            intent = parser.parse(command, [doc.name for doc in documents])
            logger.info("Resolved intent: %s value=%s", intent.action, intent.value)
            agent.handle_intent(intent)
            
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        tts.speak("Goodbye.", hardware)
    except Exception as exc:
        logger.critical("Fatal error in main loop: %s", exc)
        tts.speak("I have encountered a critical system error and need to restart. I am sorry for the interruption.", hardware)
        raise
    finally:
        # Cleanup hardware resources
        if hasattr(hardware, 'cleanup'):
            hardware.cleanup()


if __name__ == "__main__":
    run()
