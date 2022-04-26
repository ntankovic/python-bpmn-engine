# Changelog

## Unreleased

### Added

- Support for non-interruping BoundaryEvents

### Changed

- Sequence conditions can be expressions 
- Update documentation for `/extra`

### Fixed

- Fix BusinessRule Task

## [0.0.1.1] - 2022-04-26

### Changed

- Update documentation for the engine
- Update `requirements.txt`

## [0.0.1] - 2022-04-26

### Added

- Full parsing and execution support for single or multiple BoundaryEvents on Task
- Parsing support for IntermediateEvents
- Parsing support for Events subtypes - Error, Message, Timer and Terminate
- Full parsing and execution support for SubProcess
- Execution support for TerminateEndEvent 
- Execution support for TimerEvents (Start, Catch and Boundary)
- Execution support for ErrorEvents (End and Boundary)
- Execution support for catching MessageEvents (Start, Catch and Boundary)

### Changed

- Refactoring
- SendTasks are now running async correctly
- Regular EndEvents do not behave as TerminateEndEvent anymore
    - They do not consume all tokens in the process when single token arrives at it 

### Deprecated

- Multi-modal distribution check for `/extra`

### Removed

### Fixed

