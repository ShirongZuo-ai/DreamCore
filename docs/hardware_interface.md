# Hardware Interface (Placeholder)

> ⚠ This document is a placeholder. No hardware interface exists yet.
> The real interface spec will be defined once:
> - EEG hardware is selected (electrode layout, sampling rate, data format)
> - Stimulation modality is chosen (TUS, tACS, auditory, etc.)
> - Communication protocol is decided (TTL, USB, BLE, etc.)

## Intended abstraction

When hardware specs are available, we will define:

```python
# Conceptual interface — not implemented
class HardwareInterface(ABC):
    """Abstract hardware interface for DreamCore closed-loop system."""

    @abstractmethod
    def read_eeg(self) -> np.ndarray:
        """Read latest EEG buffer from device."""
        ...

    @abstractmethod
    def send_trigger(self) -> None:
        """Send stimulation trigger pulse."""
        ...

    @abstractmethod
    def get_device_info(self) -> dict:
        """Query device metadata (sampling rate, channels, etc.)."""
        ...
```

## Requirements for implementation

Before filling in this interface:

1. EEG hardware vendor + model known
2. Electrode positions and count documented
3. Sampling rate confirmed
4. Stimulation hardware chosen
5. Trigger latency budget specified
6. Safety interlocks defined

## Current state

- Mock trigger only (log lines in simulation output)
- No real hardware connected
- No signal generation for stimulation devices
