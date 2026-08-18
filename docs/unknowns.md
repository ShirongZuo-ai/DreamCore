# Unknowns

Items awaiting clarification. Do NOT code assumptions — wait for answers.

## Product & Clinical

- [ ] Target user population (healthy adults? patients with insomnia?)
- [ ] Intended clinical claim or outcome metric
- [ ] Regulatory pathway (if any)
- [ ] Required trial phases / evidence bar
- [ ] Is the device consumer wellness or medical?

## EEG Hardware

- [ ] Electrode count and positions (10-20? custom?)
- [ ] Sampling rate (100 Hz? 250 Hz? 500 Hz?)
- [ ] ADC resolution, input impedance, noise floor
- [ ] Reference scheme (mastoid, Cz, average, driven-right-leg?)
- [ ] Form factor (wearable headband? cap? dry vs. wet electrodes?)
- [ ] Onboard vs. raw data streaming bandwidth
- [ ] Manufacturer / vendor

## Ultrasound / Stimulation Interface

- [ ] Stimulation modality (TUS? tACS? auditory?)
- [ ] Transducer parameters (frequency, intensity, focus)
- [ ] Stimulation trigger latency tolerance
- [ ] Safety limits (max duty cycle, max intensity, max duration per night)
- [ ] Communication protocol (TTL? USB? BLE? I2C?)
- [ ] Does stimulation happen on up-state, down-state, or both?

## Data

- [ ] Which public dataset(s) to use for Phase 1?
  - Sleep-EDF (SC / ST)
  - MASS (SS1-SS5)
  - DREAMS
  - Montreal Archive of Sleep Studies
  - Wisconsin Sleep Cohort
- [ ] Will we collect our own pilot data? Timeline?
- [ ] Annotation reliability (single scorer? consensus?)
- [ ] Cross-dataset Eye Movement V1 sensitivity without retuning on HMC and
  ISRUC montages
- [ ] Whether ISRUC scorer disagreements should be displayed side-by-side or
  only exposed as alternate annotation metadata after V1

## Eye Movement / Sonification

- [ ] Candidate-event precision against expert-reviewed EOG intervals
- [ ] Generalization across EOG derivations, polarities, gains, and datasets
- [ ] Whether future hardware provides one or two EOG-capable channels
- [ ] Whether any montage supports defensible left/right direction inference
- [ ] Preferred musical mapping after blinded comparison studies
- [ ] MIDI/OSC/EEGsynth adapter requirements and timing tolerance

## Evaluation

- [ ] Primary success metric for phase targeting accuracy
- [ ] Acceptable phase error tolerance (in ms and degrees)
- [ ] Minimum required trigger precision / recall
- [ ] How to validate when there's no ground-truth phase (only signal)?
- [ ] Baseline methods to compare against?
