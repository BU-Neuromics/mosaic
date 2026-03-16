## 1. Expand Path Parser

- [x] 1.1 Create expand_path_parser.py module in hippo/core/
- [x] 1.2 Implement PathNode dataclass for AST representation
- [x] 1.3 Implement recursive descent parser with tokenization
- [x] 1.4 Add field identification and parent-child relationship tracking
- [x] 1.5 Implement ParsingError with descriptive messages
- [x] 1.6 Add malformed path detection (empty segments)

## 2. Cycle Detection

- [x] 2.1 Create cycle_detector.py module in hippo/core/
- [x] 2.2 Implement adjacency graph builder from parsed path
- [x] 2.3 Implement DFS-based cycle detection algorithm
- [x] 2.4 Implement CycleDetectionError with cycle path in message
- [x] 2.5 Integrate cycle detection with parser validation

## 3. Max Size Enforcement

- [x] 3.1 Add max_size parameter to parser configuration
- [x] 3.2 Implement size validation before parsing
- [x] 3.3 Implement MaxSizeExceededError with limit and actual size
- [x] 3.4 Add edge case test for path at exactly maximum size

## 4. Batch Fetcher

- [x] 4.1 Create batch_fetcher.py module in hippo/core/
- [x] 4.2 Implement entity-level query grouping
- [x] 4.3 Implement single-query-per-entity execution
- [x] 4.4 Add support for simple single-level paths
- [x] 4.5 Implement optimization for complex nested paths

## 5. Integration and Testing

- [x] 5.1 Integrate expand path parser with QueryEngine
- [x] 5.2 Add expand parameter to HippoClient API
- [x] 5.3 Write unit tests for parser
- [x] 5.4 Write unit tests for cycle detector
- [x] 5.5 Write unit tests for batch fetcher
- [x] 5.6 Write integration tests for full expand workflow
