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
    Supports optional stepper adapter when `rpi_stepper_enabled` is set.
    """
    logger = logging.getLogger(__name__)
    mode = config.hardware_mode.lower()

    # Auto-detect: Check if running on Raspberry Pi
    is_raspberry_pi = False
    if mode == "auto":
        try:
            if platform.machine().startswith('aarch64') or platform.machine().startswith('arm'):
                if Path("/proc/device-tree/model").exists():
                    model = Path("/proc/device-tree/model").read_text()
                    is_raspberry_pi = "Raspberry Pi" in model
                    logger.info("Detected hardware: %s", model.strip())
        except Exception:
            pass

    # Use RPi adapter if forced or auto-detected
    if mode == "rpi" or (mode == "auto" and is_raspberry_pi):
        # Prefer MCP23017 I2C expander adapter if configured
        try:
            if getattr(config, "mcp23017_enabled", False):
                from netra.hardware.mcp23017_stepper_adapter import MCP23017StepperAdapter
                from netra.hardware.rpi_adapter import RaspberryPiHardwareAdapter
                logger.info("Using MCP23017 I2C stepper hardware adapter")

                # Create RPi adapter for audio and camera delegation
                audio_adapter = RaspberryPiHardwareAdapter(
                    audio_device=config.rpi_audio_device,
                    audio_output_device=config.rpi_audio_output_device,
                    bt_speaker_mac=config.rpi_bt_speaker_mac,
                    scroll_button_pin=config.rpi_gpio_scroll_button,
                    status_led_pin=config.rpi_gpio_status_led,
                    servo_pins=[],  # No servos needed
                    usb_camera_device=config.usb_camera_device,
                    usb_camera_width=config.usb_camera_width,
                    usb_camera_height=config.usb_camera_height,
                )

                return MCP23017StepperAdapter(
                    chip_addresses=getattr(config, "mcp23017_addresses", None) or [0x20, 0x21],
                    total_motors=getattr(config, "mcp23017_total_motors", 8),
                    steps_per_rev=config.rpi_stepper_steps_per_revolution,
                    step_delay_sec=config.rpi_stepper_step_delay_sec,
                    audio_adapter=audio_adapter,
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("MCP23017 adapter init failed: %s, trying stepper adapter", exc)

        # Fallback: lgpio-driven stepper adapter if configured
        try:
            if getattr(config, "rpi_stepper_enabled", False) and config.rpi_stepper_motor_pins:
                from netra.hardware.stepper_adapter import StepperHardwareAdapter
                from netra.hardware.rpi_adapter import RaspberryPiHardwareAdapter
                logger.info("Using Raspberry Pi Stepper hardware adapter with audio delegation")
                
                # Create RPi adapter for audio and camera delegation (no GPIO servo setup needed)
                audio_adapter = RaspberryPiHardwareAdapter(
                    audio_device=config.rpi_audio_device,
                    audio_output_device=config.rpi_audio_output_device,
                    bt_speaker_mac=config.rpi_bt_speaker_mac,
                    scroll_button_pin=config.rpi_gpio_scroll_button,
                    status_led_pin=config.rpi_gpio_status_led,
                    servo_pins=[], # No servos for the audio adapter
                    usb_camera_device=config.usb_camera_device,
                    usb_camera_width=config.usb_camera_width,
                    usb_camera_height=config.usb_camera_height,
                )
                
                return StepperHardwareAdapter(
                    motor_pins=config.rpi_stepper_motor_pins,
                    steps_per_rev=config.rpi_stepper_steps_per_revolution,
                    step_delay_sec=config.rpi_stepper_step_delay_sec,
                    audio_adapter=audio_adapter,
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Stepper adapter init failed: %s", exc)


        try:
            from netra.hardware.rpi_adapter import RaspberryPiHardwareAdapter
            logger.info("Using Raspberry Pi hardware adapter (servo PWM)")
            servo_pins = [int(pin.strip()) for pin in str(config.rpi_gpio_servo_pins).split(",") if str(pin).strip()]
            return RaspberryPiHardwareAdapter(
                audio_device=config.rpi_audio_device,
                audio_output_device=config.rpi_audio_output_device,
                bt_speaker_mac=config.rpi_bt_speaker_mac,
                scroll_button_pin=config.rpi_gpio_scroll_button,
                status_led_pin=config.rpi_gpio_status_led,
                servo_pins=servo_pins,
                usb_camera_device=config.usb_camera_device,
                usb_camera_width=config.usb_camera_width,
                usb_camera_height=config.usb_camera_height,
            )
        except ImportError as exc:
            logger.warning("RPi adapter import failed: %s, falling back to stub", exc)

    # Fallback to stub adapter
    from netra.hardware.stub_adapter import StubHardwareAdapter
    logger.info("Using stub hardware adapter")
    return StubHardwareAdapter(
        audio_device=config.rpi_audio_device,
        sample_rate=config.audio_sample_rate,
        audio_output_device=config.rpi_audio_output_device,
        bt_speaker_mac=config.rpi_bt_speaker_mac,
    )


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
        stt_offline=getattr(config, "stt_offline", True),
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
    tts.speak_streaming(["NETRA is ready. You can speak naturally at any time."], hardware)

    if documents:
        first = ", ".join(Path(doc.name).stem.replace("_", " ") for doc in documents[:5])
        tts.speak_streaming([f"I found {len(documents)} documents. The first items are {first}"], hardware)
        logger.info("Discovered %d documents", len(documents))
    else:
        tts.speak_streaming(["I could not find any documents in your folder."], hardware)
        logger.warning("No documents found in %s", config.docs_dir)

    tts.speak_streaming(["What would you like me to do?"], hardware)

    try:
        while state.running:
            documents = docs.scan_documents()
            agent.documents = documents

            if config.enable_wake_word:
                stt.wait_for_wake(hardware, 3)
            tts.speak_streaming(["Listening for your command."], hardware)
            command = stt.listen_for_command(hardware, config.record_seconds)
            if not command.strip():
                tts.speak_streaming(["I did not catch that. Please say it again."], hardware)
                continue
            
            logger.info("User command text: %s", command)
            intent = parser.parse(command, [doc.name for doc in documents])
            logger.info("Resolved intent: %s value=%s", intent.action, intent.value)

            if intent.action == "open_not_found":
                tts.speak_streaming([f"I could not find the file {intent.value}. Should I use intelligence to process this, or do you want to try again?"], hardware)
                response = stt.listen_for_command(hardware, 5)
                if response and ("intelligence" in response.lower() or "yes" in response.lower() or "process" in response.lower()):
                    intent = parser._llm_parse(command, [doc.name for doc in documents])
                    logger.info("Resolved LLM fallback intent: %s value=%s", intent.action, intent.value)
                else:
                    tts.speak_streaming(["Okay, let's try again."], hardware)
                    continue

            agent.handle_intent(intent)
            
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        tts.speak_streaming(["Goodbye."], hardware)
    except Exception as exc:
        logger.critical("Fatal error in main loop: %s", exc)
        tts.speak_streaming(["I have encountered a critical system error and need to restart. I am sorry for the interruption."], hardware)
        raise
    finally:
        # Cleanup hardware resources
        if hasattr(hardware, 'cleanup'):
            hardware.cleanup()


if __name__ == "__main__":
    run()
