## 1. Core DDL Generator Implementation

- [x] 1.1 Create DDLGenerator class in hippo/core/storage/ directory
- [x] 1.2 Implement basic table generation from SchemaConfig entity
- [x] 1.3 Add support for PRIMARY KEY constraint generation
- [x] 1.4 Add support for is_available column with DEFAULT 1

## 2. Constraint Support

- [x] 2.1 Implement FOREIGN KEY constraint generation
- [x] 2.2 Implement UNIQUE constraint generation
- [x] 2.3 Implement DEFAULT value generation
- [x] 2.4 Implement INDEX generation with partial index support

## 3. Type Mapping

- [x] 3.1 Implement datetime to TEXT type mapping
- [x] 3.2 Implement boolean to INTEGER type mapping
- [x] 3.3 Add unit tests for type mapping

## 4. Inheritance Support

- [x] 4.1 Implement class-table inheritance strategy
- [x] 4.2 Generate child tables with foreign key to parent
- [x] 4.3 Add inheritance test cases

## 5. Dependency Ordering

- [x] 5.1 Implement topological sort for table dependencies
- [x] 5.2 Generate tables in correct foreign key order
- [x] 5.3 Add integration test for multi-entity schema generation
