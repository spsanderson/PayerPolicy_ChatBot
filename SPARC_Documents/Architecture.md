# Architecture

## Objective
Define the comprehensive system architecture and technical design for the RAG Ollama Application, detailing the layered architecture, component interactions, data flows, and deployment strategies for a production-ready web-based document Q&A system.

---

## Architectural Style

**Layered Architecture with Service-Oriented Design**

The application follows a **5-layer architecture** pattern that provides clear separation of concerns, maintainability, and testability:

1. **Presentation Layer** - Web UI and user interactions
2. **API Layer** - RESTful endpoints and request handling
3. **Business Logic Layer** - Core RAG pipeline and document processing
4. **Data Access Layer** - Vector database and file system operations
5. **External Services Layer** - Ollama integration and system resources

This architecture is chosen for its:
- **Modularity**: Each layer has distinct responsibilities
- **Testability**: Layers can be tested independently
- **Maintainability**: Changes in one layer minimally impact others
- **Scalability**: Individual components can be optimized or scaled independently
- **API-First Design**: Web-accessible REST API with flexible deployment options

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │   Chat UI    │  │  Upload UI   │  │  Document Management UI  │ │
│  │  (HTML/CSS/  │  │  (Drag-Drop) │  │   (List/Search/Delete)   │ │
│  │  JavaScript) │  │              │  │                          │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘ │
└─────────┼──────────────────┼──────────────────────┼─────────────────┘
          │                  │                      │
          │ HTTP/REST        │ HTTP/REST            │ HTTP/REST
          │                  │                      │
┌─────────┼──────────────────┼──────────────────────┼─────────────────┐
│         │              API LAYER (Flask)          │                 │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌───────────▼──────────┐     │
│  │ /api/chat    │  │ /api/upload  │  │ /api/documents       │     │
│  │ - POST       │  │ - POST       │  │ - GET/DELETE         │     │
│  │ - Streaming  │  │ - Multipart  │  │ - Pagination         │     │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬──────────┘     │
│         │                  │                      │                 │
│  ┌──────▼──────────────────▼──────────────────────▼──────────┐     │
│  │         Authentication & Authorization Middleware          │     │
│  │              Rate Limiting & Request Validation            │     │
│  │                   CORS Configuration                       │     │
│  └────────────────────────────┬───────────────────────────────┘     │
└───────────────────────────────┼─────────────────────────────────────┘
                                │
┌───────────────────────────────┼─────────────────────────────────────┐
│                    BUSINESS LOGIC LAYER                             │
│  ┌────────────────────────────▼──────────────────────────────────┐ │
│  │                    RAG Pipeline Orchestrator                   │ │
│  │  - Query Processing  - Context Building  - Response Generation│ │
│  └─────┬──────────────────┬──────────────────┬───────────────────┘ │
│        │                  │                  │                     │
│  ┌─────▼──────────┐ ┌─────▼──────────┐ ┌────▼──────────────────┐ │
│  │   Document     │ │   Embedding    │ │   LLM Response        │ │
│  │   Processor    │ │   Generator    │ │   Generator           │ │
│  │ - PDF Extract  │ │ - Batch Process│ │ - Prompt Construction │ │
│  │ - Excel Extract│ │ - Caching      │ │ - Citation Addition   │ │
│  │ - Chunking     │ │ - Normalization│ │ - Streaming Support   │ │
│  └────────────────┘ └────────────────┘ └───────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                │
┌───────────────────────────────┼─────────────────────────────────────┐
│                      DATA ACCESS LAYER                              │
│  ┌────────────────────────────▼──────────────────────────────────┐ │
│  │                    Data Access Abstraction                     │ │
│  └─────┬──────────────────┬──────────────────┬───────────────────┘ │
│        │                  │                  │                     │
│  ┌─────▼──────────┐ ┌─────▼──────────┐ ┌────▼──────────────────┐ │
│  │  Vector Store  │ │  File Storage  │ │  Metadata Database    │ │
│  │  Interface     │ │  Manager       │ │  (SQLite)             │ │
│  │ - Add Docs     │ │ - Upload       │ │ - Documents Table     │ │
│  │ - Search       │ │ - Retrieve     │ │ - Conversations Table │ │
│  │ - Delete       │ │ - Delete       │ │ - Messages Table      │ │
│  └────────────────┘ └────────────────┘ └───────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                │
┌───────────────────────────────┼─────────────────────────────────────┐
│                   EXTERNAL SERVICES LAYER                           │
│  ┌────────────────────────────▼──────────────────────────────────┐ │
│  │                    Service Connectors                          │ │
│  └─────┬──────────────────┬──────────────────┬───────────────────┘ │
│        │                  │                  │                     │
│  ┌─────▼──────────┐ ┌─────▼──────────┐ ┌────▼──────────────────┐ │
│  │  Ollama API    │ │   ChromaDB     │ │   File System         │ │
│  │  ${OLLAMA_     │ │   Local/Cloud  │ │   /data/uploads       │ │
│  │  BASE_URL}     │ │   Store        │ │   /data/processed     │ │
│  │ - Embeddings   │ │ - HNSW Index   │ │   /data/vector_db     │ │
│  │ - Generation   │ │ - Cosine Sim   │ │   /logs               │ │
│  └────────────────┘ └────────────────┘ └───────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────────┐
                    │   Monitoring & Logging   │
                    │  - Prometheus Metrics    │
                    │  - Application Logs      │
                    │  - Performance Tracking  │
                    └──────────────────────────┘
```

---

## Technology Stack

### Backend Framework
- **Flask 3.0+**: Lightweight, flexible web framework
  - Chosen for simplicity and ease of deployment
  - Supports both synchronous and asynchronous operations
  - Extensive ecosystem of extensions
  - Lower resource footprint than Django

### Document Processing
- **PyPDF2 / pdfplumber**: PDF text extraction
  - PyPDF2: Fast, lightweight for simple PDFs
  - pdfplumber: Better handling of complex layouts and tables
- **openpyxl**: Excel file processing
  - Native Python library, no external dependencies
  - Supports both .xlsx and .xls formats
  - Handles formulas, formatting, and multiple sheets

### Vector Database
- **ChromaDB**: Local vector database
  - Embedded database, no separate server required
  - Built-in HNSW indexing for fast similarity search
  - Persistent storage with SQLite backend
  - Native Python integration
  - Supports metadata filtering

### LLM Integration
- **Ollama**: Local LLM inference server
  - Runs models locally without API costs
  - Supports multiple models (Llama 2, Mistral, etc.)
  - REST API for easy integration
  - GPU acceleration support
  - Model: **nomic-embed-text** for embeddings (768 dimensions)
  - Model: **llama2** or **mistral** for text generation

### Metadata Storage
- **SQLite**: Lightweight relational database
  - Serverless, zero-configuration
  - File-based storage
  - ACID compliant
  - Sufficient for metadata and conversation history

### Frontend
- **HTML5/CSS3**: Modern web standards
- **JavaScript (ES6+)**: Client-side interactivity
  - Vanilla JS for minimal dependencies
  - Optional: React/Vue.js for complex UI needs
- **Server-Sent Events (SSE)**: Real-time streaming responses

### Development & Deployment
- **Python 3.10+**: Modern Python features and performance
- **pip/virtualenv**: Dependency management
- **Gunicorn**: Production WSGI server
- **Nginx**: Reverse proxy and static file serving
- **systemd**: Service management on Linux
- **Docker** (optional): Containerization for easier deployment

### Monitoring & Logging
- **Python logging**: Built-in logging framework
- **Prometheus**: Metrics collection
- **Grafana** (optional): Metrics visualization

---

## Data Models and Schemas

### Document Metadata Model

```python
Document {
    document_id: UUID (Primary Key)
    filename: String (max 255 chars)
    file_type: Enum ['pdf', 'excel']
    file_size: Integer (bytes)
    upload_date: Timestamp
    user_id: UUID (Foreign Key)
    status: Enum ['processing', 'indexed', 'failed']
    chunk_count: Integer
    file_path: String (file system path)
    created_at: Timestamp
    updated_at: Timestamp
}
```

### Document Chunk Model (Vector Database)

```python
DocumentChunk {
    chunk_id: UUID (Primary Key)
    document_id: UUID (Foreign Key)
    chunk_index: Integer
    text: String (chunk content)
    embedding: Vector[768] (nomic-embed-text dimension)
    token_count: Integer
    metadata: {
        filename: String
        file_type: String
        upload_date: Timestamp
        page_number: Integer (for PDFs)
        sheet_name: String (for Excel)
    }
}
```

### User Model

```python
User {
    user_id: UUID (Primary Key)
    username: String (unique, max 50 chars)
    email: String (unique, max 255 chars)
    hashed_password: String (bcrypt hash)
    role: Enum ['user', 'admin']
    is_active: Boolean (default: True)
    created_at: Timestamp
    last_login: Timestamp
}
```

### Conversation Model

```python
Conversation {
    conversation_id: UUID (Primary Key)
    user_id: UUID (Foreign Key)
    created_at: Timestamp
    last_updated: Timestamp
    message_count: Integer
}
```

### Message Model

```python
Message {
    message_id: UUID (Primary Key)
    conversation_id: UUID (Foreign Key)
    role: Enum ['user', 'assistant']
    content: Text
    sources: JSON (array of source document references)
    timestamp: Timestamp
    query_time: Float (seconds, for assistant messages)
}
```

### API Request/Response Schemas

**Chat Request:**
```json
{
    "query": "string (required, 3-1000 chars)",
    "conversation_id": "uuid (optional)"
}
```

**Chat Response:**
```json
{
    "status": "success",
    "data": {
        "conversation_id": "uuid",
        "answer": "string with [citations]",
        "sources": [
            {
                "number": 1,
                "filename": "string",
                "text": "string (snippet)",
                "score": 0.92,
                "document_id": "uuid"
            }
        ],
        "metadata": {
            "query_time": 2.3,
            "num_sources": 2,
            "model": "llama2"
        }
    }
}
```

**Upload Response:**
```json
{
    "status": "success",
    "data": {
        "uploaded": 2,
        "failed": 0,
        "details": [
            {
                "filename": "report.pdf",
                "document_id": "uuid",
                "status": "success"
            }
        ]
    }
}
```

---

## Key Components

### 1. RAG Pipeline Orchestrator

**Responsibilities:**
- Coordinate the entire query-to-answer workflow
- Manage error handling and retry logic
- Track performance metrics
- Handle conversation context

**Key Methods:**
- `process_rag_query(query, conversation_id)`: Main entry point
- `validate_query(query)`: Input validation
- `build_context(chunks)`: Context construction
- `add_citations(answer, sources)`: Citation management

**Dependencies:**
- Embedding Generator
- Vector Store Interface
- LLM Response Generator

---

### 2. Document Processor

**Responsibilities:**
- Extract text from various document formats
- Implement intelligent chunking strategies
- Preserve document structure and metadata
- Handle processing errors gracefully

**Sub-components:**
- **PDF Processor**: Extracts text from PDF files, handles multi-page documents
- **Excel Processor**: Extracts text from spreadsheets, processes multiple sheets
- **Text Chunker**: Splits documents into semantic chunks with overlap

**Key Methods:**
- `extract_text_from_document(file_path, file_type)`
- `chunk_document(text, metadata, chunk_size, overlap)`
- `split_into_paragraphs(text)`
- `create_chunk_object(text, index, metadata)`

---

### 3. Embedding Generator

**Responsibilities:**
- Generate embeddings using Ollama's nomic-embed-text model
- Implement batching for efficiency
- Cache embeddings to avoid redundant computation
- Handle Ollama service failures with retry logic

**Key Methods:**
- `generate_embedding(text, client)`
- `generate_embeddings_batch(texts, client, batch_size)`
- `normalize_vector(vector)`
- `check_ollama_health(client)`

**Performance Optimizations:**
- Batch processing (32 texts per batch)
- LRU caching for frequently used embeddings
- Connection pooling to Ollama service
- Exponential backoff on failures

---

### 4. Vector Store Interface

**Responsibilities:**
- Abstract ChromaDB operations
- Provide consistent API for vector operations
- Manage collections and indices
- Handle metadata filtering

**Key Methods:**
- `initialize_vector_database(db_path, collection_name)`
- `add_documents_to_vector_db(chunks, embeddings, collection)`
- `search_similar_documents(query_embedding, collection, top_k, threshold)`
- `delete_chunks_by_document_id(collection, document_id)`

**Index Configuration:**
- HNSW (Hierarchical Navigable Small World) algorithm
- Cosine similarity metric
- M=16, ef_construction=200 for balanced performance

---

### 5. LLM Response Generator

**Responsibilities:**
- Construct effective prompts for RAG
- Generate responses using Ollama LLM
- Support streaming responses
- Manage context window limitations

**Key Methods:**
- `generate_llm_response(prompt, client)`
- `generate_llm_response_streaming(prompt, client)`
- `create_rag_prompt(query, context, chunks)`
- `get_prompt_template()`

**Prompt Engineering:**
- Clear instructions to use only provided context
- Citation requirements
- Handling of insufficient information
- Stop sequences to prevent over-generation

---

### 6. Authentication & Authorization Module

**Responsibilities:**
- User authentication with JWT tokens
- Role-based access control
- Session management
- Rate limiting per user

**Key Methods:**
- `authenticate_user(username, password)`
- `create_access_token(user_id, username, role)`
- `verify_access_token(token)`
- `get_current_user(request)`

**Security Features:**
- Bcrypt password hashing
- JWT with expiration (1 hour default)
- Token refresh mechanism
- Role-based permissions (user, admin)

---

### 7. File Storage Manager

**Responsibilities:**
- Handle file uploads and validation
- Manage temporary and permanent storage
- Organize files by document ID
- Clean up orphaned files

**Key Methods:**
- `save_to_temp_storage(file)`
- `move_to_permanent_storage(temp_path, document_id)`
- `delete_file(file_path)`
- `validate_file_type(file)`

**Storage Structure:**
```
data/
├── uploads/          # Temporary upload storage
├── processed/        # Permanent document storage
│   ├── {doc_id}_filename.pdf
│   └── {doc_id}_filename.xlsx
└── vector_db/        # ChromaDB persistence
    └── chroma.sqlite3
```

---

### 8. Caching Layer

**Responsibilities:**
- Cache query results to improve response time
- Cache embeddings to reduce Ollama calls
- Implement LRU eviction policy
- Manage cache size and TTL

**Cache Types:**
- **Query Cache**: Stores complete RAG responses (TTL: 1 hour)
- **Embedding Cache**: Stores text embeddings (TTL: 24 hours)
- **Document Metadata Cache**: Frequently accessed metadata (TTL: 6 hours)

**Implementation:**
- In-memory Python dictionaries with TTL tracking
- Optional: Redis for distributed caching in scaled deployments

---

## Data Flow Diagrams

### Query Processing Flow (Detailed)

```
┌─────────────┐
│ User Query  │
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│ API Layer               │
│ - Validate input        │
│ - Authenticate user     │
│ - Rate limit check      │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Check Query Cache       │
└──────┬──────────────────┘
       │
       ├─── Cache Hit ────────────────┐
       │                              │
       ▼ Cache Miss                   ▼
┌─────────────────────────┐    ┌──────────────┐
│ Generate Query          │    │ Return       │
│ Embedding               │    │ Cached       │
│ (Ollama API)            │    │ Response     │
└──────┬──────────────────┘    └──────────────┘
       │
       ▼
┌─────────────────────────┐
│ Vector Similarity       │
│ Search (ChromaDB)       │
│ - Top-K retrieval       │
│ - Threshold filtering   │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Re-rank Results         │
│ (Optional)              │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Build Context           │
│ - Select chunks         │
│ - Respect token limit   │
│ - Format for prompt     │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Construct RAG Prompt    │
│ - Add instructions      │
│ - Include context       │
│ - Add user query        │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Generate Response       │
│ (Ollama LLM)            │
│ - Stream tokens         │
│ - Apply stop sequences  │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Add Citations           │
│ - Parse answer          │
│ - Match to sources      │
│ - Format citations      │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Cache Response          │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Log Conversation        │
│ - Save to database      │
│ - Track analytics       │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Return to User          │
│ - Answer with citations │
│ - Source documents      │
│ - Metadata              │
└─────────────────────────┘
```

### Document Ingestion Flow (Detailed)

```
┌─────────────┐
│ File Upload │
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│ API Layer               │
│ - Validate file type    │
│ - Check file size       │
│ - Authenticate user     │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Save to Temp Storage    │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Create Document Record  │
│ - Generate UUID         │
│ - Status: 'processing'  │
│ - Save metadata         │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Extract Text            │
│ - PDF: pdfplumber       │
│ - Excel: openpyxl       │
│ - Preserve structure    │
└──────┬──────────────────┘
       │
       ├─── Error ─────────────────┐
       │                           │
       ▼                           ▼
┌─────────────────────────┐  ┌──────────────┐
│ Chunk Document          │  │ Update Status│
│ - Split paragraphs      │  │ to 'failed'  │
│ - Apply overlap         │  └──────────────┘
│ - Create chunk objects  │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Generate Embeddings     │
│ - Batch processing      │
│ - 32 chunks per batch   │
│ - Ollama API calls      │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Store in Vector DB      │
│ - Add to ChromaDB       │
│ - Include metadata      │
│ - Update indices        │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Move to Permanent       │
│ Storage                 │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Update Document Record  │
│ - Status: 'indexed'     │
│ - Chunk count           │
│ - File path             │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Return Success Response │
│ - Document ID           │
│ - Processing stats      │
└─────────────────────────┘
```

---

## Scalability, Security, and Performance

### Scalability

**Current Design (Single Server):**
- Handles 7,500+ documents efficiently
- Supports 10 concurrent users
- Vertical scaling through hardware upgrades

**Horizontal Scaling Path:**

1. **Load Balancing:**
   - Deploy multiple Flask instances behind Nginx
   - Use session affinity for conversation continuity
   - Shared file storage (NFS or object storage)

2. **Database Scaling:**
   - Shard ChromaDB by document categories
   - Implement read replicas for query-heavy workloads
   - Use Redis for distributed caching

3. **Ollama Scaling:**
   - Deploy multiple Ollama instances
   - Implement request routing based on load
   - Use GPU clusters for faster inference

**Performance Targets:**
- Query response time: < 5 seconds (95th percentile)
- Document indexing: > 10 documents/minute
- Concurrent users: 10+ (single server)
- Vector search latency: < 500ms for 7,500+ documents

**Bottleneck Analysis:**
- **Primary**: Ollama LLM generation (2-4 seconds)
- **Secondary**: Embedding generation for large batches
- **Tertiary**: Vector search for very large collections

**Optimization Strategies:**
- Implement aggressive caching for common queries
- Use smaller, faster models for simple queries
- Pre-compute embeddings during off-peak hours
- Implement query result pagination

---

### Security

**Authentication & Authorization:**
- JWT-based authentication with 1-hour expiration
- Bcrypt password hashing (cost factor: 12)
- Role-based access control (RBAC)
- Session management with secure cookies

**Input Validation:**
- File type whitelist (PDF, Excel only)
- File size limits (100MB maximum)
- Query length validation (3-1000 characters)
- SQL injection prevention (parameterized queries)
- XSS prevention (input sanitization)

**Data Protection:**
- All data stored locally (no external transmission)
- File system permissions (read/write restricted to app user)
- Database encryption at rest (optional)
- Secure file upload handling (temporary directory isolation)

**Network Security:**
- HTTPS only in production (TLS 1.3)
- CORS configuration for API endpoints
- Rate limiting per user (100 requests/hour)
- Request size limits (100MB for uploads)

**Prompt Injection Prevention:**
```python
def detect_prompt_injection(query):
    dangerous_patterns = [
        'ignore previous instructions',
        'disregard all',
        'system prompt',
        'you are now',
        '<script>',
        'javascript:'
    ]
    
    query_lower = query.lower()
    for pattern in dangerous_patterns:
        if pattern in query_lower:
            raise SecurityError("Potential prompt injection detected")
```

**Security Headers:**
```python
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    return response
```

---

### Performance

**Caching Strategy:**

1. **Query Cache:**
   - Cache complete RAG responses
   - TTL: 1 hour
   - Max size: 1000 entries
   - LRU eviction policy

2. **Embedding Cache:**
   - Cache text embeddings
   - TTL: 24 hours
   - Max size: 10,000 entries
   - Reduces Ollama API calls by ~60%

3. **Metadata Cache:**
   - Cache document metadata
   - TTL: 6 hours
   - Reduces database queries

**Database Optimization:**

1. **ChromaDB:**
   - HNSW index for fast approximate search
   - Cosine similarity metric
   - Batch insertions for efficiency
   - Periodic index rebuilding

2. **SQLite:**
   - Indexed columns: document_id, user_id, conversation_id
   - WAL mode for better concurrency
   - Pragma optimizations:
     ```sql
     PRAGMA journal_mode=WAL;
     PRAGMA synchronous=NORMAL;
     PRAGMA cache_size=10000;
     ```

**Batch Processing:**
- Embedding generation: 32 texts per batch
- Document ingestion: Parallel processing with multiprocessing
- Vector insertion: Batch inserts of 100+ chunks

**Asynchronous Operations:**
- Document processing runs in background
- Long-running queries use streaming responses
- File uploads processed asynchronously

**Resource Management:**
- Connection pooling for database connections
- Request queuing to prevent overload
- Memory limits for large file processing
- Automatic cleanup of temporary files

**Monitoring Metrics:**
```python
# Key performance indicators
- query_duration_seconds (histogram)
- embedding_generation_seconds (histogram)
- vector_search_seconds (histogram)
- llm_generation_seconds (histogram)
- cache_hit_rate (gauge)
- active_users (gauge)
- documents_total (gauge)
- cpu_usage_percent (gauge)
- memory_usage_percent (gauge)
```

---

## Deployment Architecture

### Single Server Deployment

```
┌────────────────────────────────────────────────────────┐
│                    Linux Server                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │              Nginx (Reverse Proxy)               │  │
│  │  - Port 80/443                                   │  │
│  │  - SSL Termination                               │  │
│  │  - Static file serving                           │  │
│  │  - Load balancing (if multiple Gunicorn workers) │  │
│  └────────────────┬─────────────────────────────────┘  │
│                   │                                    │
│  ┌────────────────▼─────────────────────────────────┐  │
│  │         Gunicorn (WSGI Server)                   │  │
│  │  - 4 worker processes                            │  │
│  │  - Port 5000 (internal)                          │  │
│  │  - Timeout: 120 seconds                          │  │
│  └────────────────┬─────────────────────────────────┘  │
│                   │                                    │
│  ┌────────────────▼─────────────────────────────────┐  │
│  │         Flask Application                        │  │
│  │  - RAG Pipeline                                  │  │
│  │  - API Endpoints                                 │  │
│  │  - Business Logic                                │  │
│  └─────┬──────────────────┬─────────────────────────┘  │
│        │                  │                            │
│  ┌─────▼──────────┐ ┌─────▼──────────┐                 │
│  │  ChromaDB      │ │  SQLite        │                 │
│  │  (Vector DB)   │ │  (Metadata)    │                 │
│  └────────────────┘ └────────────────┘                 │
│                                                        │
│  ┌───────────────────────────────────────────────────┐ │
│  │         Ollama Service                            │ │
│  │  - Port 11434                                     │ │
│  │  - Models: nomic-embed-text, llama2               │ │
│  │  - GPU acceleration (if available)                │ │
│  └───────────────────────────────────────────────────┘ │
│                                                        │
│  ┌───────────────────────────────────────────────────┐ │
│  │         File System Storage                       │ │
│  │  /data/uploads/     - Temporary uploads           │ │
│  │  /data/processed/   - Permanent documents         │ │
│  │  /data/vector_db/   - ChromaDB persistence        │ │
│  │  /logs/             - Application logs            │ │
│  └───────────────────────────────────────────────────┘ │
│                                                        │
│  ┌───────────────────────────────────────────────────┐ │
│  │         Systemd Services                          │ │
│  │  - rag-app.service    (Flask application)         │ │
│  │  - ollama.service     (Ollama server)             │ │
│  │  - nginx.service      (Web server)                │ │
│  └───────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

### Docker Deployment (Optional)

```yaml
# docker-compose.yml
version: '3.8'

services:
  rag-app:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - VECTOR_DB_PATH=/app/data/vector_db
    depends_on:
      - ollama
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./static:/usr/share/nginx/html/static
    depends_on:
      - rag-app
    restart: unless-stopped

volumes:
  ollama_data:
```

---

### Cloud Deployment Architecture

#### AWS Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AWS Cloud Infrastructure                 │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │            CloudFront (CDN)                         │   │
│  │  - Global content delivery                          │   │
│  │  - HTTPS/SSL termination                            │   │
│  └─────────────────┬───────────────────────────────────┘   │
│                    │                                        │
│  ┌─────────────────▼───────────────────────────────────┐   │
│  │      Application Load Balancer (ALB)                │   │
│  │  - Health checks: /api/health                       │   │
│  │  - Target groups                                    │   │
│  │  - SSL termination (ACM certificate)                │   │
│  └───────────┬──────────────────┬──────────────────────┘   │
│              │                  │                           │
│  ┌───────────▼────────┐  ┌──────▼───────────┐              │
│  │   ECS Fargate      │  │  ECS Fargate     │              │
│  │   Task (App)       │  │  Task (App)      │              │
│  │  - Docker container│  │ - Docker container│              │
│  │  - Auto-scaling    │  │ - Auto-scaling   │              │
│  └───────────┬────────┘  └──────┬───────────┘              │
│              │                  │                           │
│              ├──────────────────┘                           │
│              │                                              │
│  ┌───────────▼─────────────────────────────────────────┐   │
│  │              Shared Services                        │   │
│  │  ┌────────────────┐  ┌────────────────┐             │   │
│  │  │  S3 Bucket     │  │  RDS PostgreSQL│             │   │
│  │  │  (Documents)   │  │  (Metadata)    │             │   │
│  │  └────────────────┘  └────────────────┘             │   │
│  │  ┌────────────────┐  ┌────────────────┐             │   │
│  │  │ElastiCache     │  │  EC2 Instance  │             │   │
│  │  │(Redis/Cache)   │  │  (Ollama GPU)  │             │   │
│  │  └────────────────┘  └────────────────┘             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Monitoring & Logging                      │   │
│  │  - CloudWatch Logs & Metrics                        │   │
│  │  - X-Ray (Distributed tracing)                      │   │
│  │  - SNS Alerts                                       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

#### Kubernetes Architecture

```
┌───────────────────────────────────────────────────────────┐
│             Kubernetes Cluster (GKE/EKS/AKS)             │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │            Ingress Controller (Nginx)               │ │
│  │  - HTTPS/TLS termination                            │ │
│  │  - Path-based routing                               │ │
│  │  - Rate limiting                                    │ │
│  └─────────────────┬───────────────────────────────────┘ │
│                    │                                      │
│  ┌─────────────────▼───────────────────────────────────┐ │
│  │         Service: rag-ollama-app-service             │ │
│  │  - Type: LoadBalancer                               │ │
│  │  - Port: 80 → 5000                                  │ │
│  └───────┬─────────────────┬───────────────────────────┘ │
│          │                 │                             │
│  ┌───────▼─────┐  ┌────────▼──────┐  ┌──────────────┐  │
│  │   Pod 1     │  │    Pod 2      │  │    Pod 3     │  │
│  │ (RAG App)   │  │  (RAG App)    │  │  (RAG App)   │  │
│  │ + Sidecar   │  │  + Sidecar    │  │  + Sidecar   │  │
│  └─────┬───────┘  └────────┬──────┘  └──────┬───────┘  │
│        │                   │                 │          │
│        └───────────────────┴─────────────────┘          │
│                            │                            │
│  ┌─────────────────────────▼─────────────────────────┐  │
│  │           Persistent Volumes (PVC)                 │  │
│  │  - Documents: ReadWriteMany (NFS/EFS)              │  │
│  │  - Vector DB: ReadWriteOnce (SSD)                  │  │
│  │  - Logs: ReadWriteMany                             │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │           ConfigMaps & Secrets                     │  │
│  │  - API keys, JWT secrets                           │  │
│  │  - Environment configuration                       │  │
│  │  - CORS origins                                    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │        External Services (StatefulSet)             │  │
│  │  ┌──────────────┐        ┌──────────────┐          │  │
│  │  │  PostgreSQL  │        │   Ollama     │          │  │
│  │  │  (Metadata)  │        │   (GPU Pod)  │          │  │
│  │  └──────────────┘        └──────────────┘          │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │    Horizontal Pod Autoscaler (HPA)                 │  │
│  │  - CPU: 70% threshold                              │  │
│  │  - Memory: 80% threshold                           │  │
│  │  - Min replicas: 3, Max: 10                        │  │
│  └────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

#### Multi-Region Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Global Traffic Manager                    │
│              (Route 53 / Azure Traffic Manager)             │
│          Geo-routing + Health checks + Failover             │
└───────────┬─────────────────────────┬───────────────────────┘
            │                         │
    ┌───────▼────────┐        ┌───────▼────────┐
    │  Region: US    │        │  Region: EU    │
    │  (Primary)     │        │  (Secondary)   │
    │                │        │                │
    │  ┌──────────┐  │        │  ┌──────────┐  │
    │  │  ALB/LB  │  │        │  │  ALB/LB  │  │
    │  └────┬─────┘  │        │  └────┬─────┘  │
    │       │        │        │       │        │
    │  ┌────▼─────┐  │        │  ┌────▼─────┐  │
    │  │ App Tier │  │        │  │ App Tier │  │
    │  │ (3 nodes)│  │        │  │ (3 nodes)│  │
    │  └────┬─────┘  │        │  └────┬─────┘  │
    │       │        │        │       │        │
    │  ┌────▼─────┐  │        │  ┌────▼─────┐  │
    │  │  Cache   │  │        │  │  Cache   │  │
    │  │  (Redis) │  │        │  │  (Redis) │  │
    │  └────┬─────┘  │        │  └────┬─────┘  │
    │       │        │        │       │        │
    │  ┌────▼─────┐  │        │  ┌────▼─────┐  │
    │  │ Database │◄─┼────────┼─►│ Database │  │
    │  │(Primary) │  │   Repl │  │(Replica) │  │
    │  └──────────┘  │        │  └──────────┘  │
    │                │        │                │
    │  ┌──────────┐  │        │  ┌──────────┐  │
    │  │ Storage  │◄─┼────────┼─►│ Storage  │  │
    │  │  (S3)    │  │  Sync  │  │  (S3)    │  │
    │  └──────────┘  │        │  └──────────┘  │
    └────────────────┘        └────────────────┘
```

---

## Component Interaction Patterns

### Request-Response Pattern (Synchronous)

```
Client → API Layer → Business Logic → Data Access → External Service
                                                            ↓
Client ← API Layer ← Business Logic ← Data Access ← External Service
```

**Use Cases:**
- Document metadata retrieval
- User authentication
- Document deletion
- Health checks

### Streaming Pattern (Asynchronous)

```
Client ← SSE Stream ← API Layer ← LLM Generator ← Ollama
         (tokens)
```

**Use Cases:**
- Real-time chat responses
- Long-running LLM generation
- Improved perceived performance

### Background Processing Pattern

```
Client → API Layer → Queue → Background Worker → Data Access
   ↓                                                    ↓
Response (202 Accepted)                          Processing Complete
```

**Use Cases:**
- Document ingestion
- Batch embedding generation
- Large file processing

### Caching Pattern

```
Request → Cache Check → [Hit] → Return Cached Data
              ↓
            [Miss]
              ↓
         Process Request → Update Cache → Return Data
```

**Use Cases:**
- Query results
- Embeddings
- Document metadata

---

## Error Handling Architecture

### Error Propagation Strategy

```
┌─────────────────────────────────────────────────────┐
│              Error Handling Layers                  │
├─────────────────────────────────────────────────────┤
│  Presentation Layer                                 │
│  - Display user-friendly messages                   │
│  - Show retry options                               │
│  - Log client-side errors                           │
├─────────────────────────────────────────────────────┤
│  API Layer                                          │
│  - Catch all exceptions                             │
│  - Map to HTTP status codes                         │
│  - Return structured error responses                │
│  - Log request context                              │
├─────────────────────────────────────────────────────┤
│  Business Logic Layer                               │
│  - Raise domain-specific exceptions                 │
│  - Implement retry logic                            │
│  - Validate business rules                          │
│  - Log processing errors                            │
├─────────────────────────────────────────────────────┤
│  Data Access Layer                                  │
│  - Handle database errors                           │
│  - Manage connection failures                       │
│  - Implement circuit breakers                       │
│  - Log data access errors                           │
├─────────────────────────────────────────────────────┤
│  External Services Layer                            │
│  - Handle service unavailability                    │
│  - Implement exponential backoff                    │
│  - Timeout management                               │
│  - Log external service errors                      │
└─────────────────────────────────────────────────────┘
```

### Circuit Breaker Pattern

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        if self.state == 'OPEN':
            if time.time() - self.last_failure_time > self.timeout:
                self.state = 'HALF_OPEN'
            else:
                raise CircuitBreakerOpenError()
        
        try:
            result = func(*args, **kwargs)
            if self.state == 'HALF_OPEN':
                self.state = 'CLOSED'
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = 'OPEN'
            
            raise e
```

---

## Monitoring and Observability Architecture

### Metrics Collection

```
┌─────────────────────────────────────────────────────┐
│           Application Instrumentation               │
│  - Request counters                                 │
│  - Duration histograms                              │
│  - Error rates                                      │
│  - Resource usage gauges                            │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│         Prometheus Metrics Endpoint                 │
│         /metrics (text/plain)                       │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│         Prometheus Server (Scraping)                │
│  - Scrape interval: 15 seconds                      │
│  - Retention: 15 days                               │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│         Grafana Dashboard (Visualization)           │
│  - Real-time metrics                                │
│  - Historical trends                                │
│  - Alerting rules                                   │
└─────────────────────────────────────────────────────┘
```

### Logging Architecture

```
┌─────────────────────────────────────────────────────┐
│           Application Logging                       │
│  - Structured JSON logs                             │
│  - Multiple log levels (INFO, WARNING, ERROR)       │
│  - Contextual information                           │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│         Log Files (Rotating)                        │
│  - app.log (10MB, 10 backups)                       │
│  - error.log (daily rotation, 30 days)              │
│  - performance.log (10MB, 5 backups)                │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│         Log Aggregation (Optional)                  │
│  - ELK Stack (Elasticsearch, Logstash, Kibana)      │
│  - Centralized log management                       │
│  - Advanced search and analysis                     │
└─────────────────────────────────────────────────────┘
```

---

## Reflection

### Choice of Flask

**Rationale:**
- **Simplicity**: Minimal boilerplate, easy to understand and maintain
- **Flexibility**: Not opinionated, allows custom architecture
- **Lightweight**: Lower resource footprint than Django
- **Ecosystem**: Extensive library support and community
- **Synchronous by default**: Simpler to reason about for RAG pipeline

**Alternatives Considered:**
- **FastAPI**: More modern, async-first, but adds complexity for this use case
- **Django**: Too heavyweight for this application's needs
- **Tornado**: Good for async, but less mature ecosystem

### Choice of ChromaDB

**Rationale:**
- **Embedded**: No separate server to manage
- **Local-first**: Aligns with privacy requirements
- **Python-native**: Seamless integration
- **Performance**: HNSW indexing provides fast similarity search
- **Persistence**: Built-in SQLite backend

**Alternatives Considered:**
- **FAISS**: Faster but requires more manual management
- **Qdrant**: Excellent but requires separate server
- **Weaviate**: Feature-rich but complex for initial web-based deployment
- **Pinecone**: Cloud-only, violates privacy requirement

### Choice of Ollama

**Rationale:**
- **Local inference**: No external API calls, complete privacy
- **Easy setup**: Simple installation and model management
- **Multiple models**: Flexibility to choose appropriate model
- **REST API**: Easy integration with any language
- **Active development**: Regular updates and improvements

**Alternatives Considered:**
- **llama.cpp**: Lower-level, requires more integration work
- **LocalAI**: Similar but less mature
- **Hugging Face Transformers**: More complex setup and management

### Architectural Trade-offs

**Monolithic vs. Microservices:**
- **Chosen**: Monolithic (layered architecture)
- **Rationale**: Simpler deployment, lower operational overhead, sufficient for scale
- **Trade-off**: Less flexibility for independent scaling of components

**Synchronous vs. Asynchronous:**
- **Chosen**: Primarily synchronous with streaming for LLM responses
- **Rationale**: Simpler code, easier debugging, sufficient performance
- **Trade-off**: Lower theoretical maximum throughput

**In-Memory vs. Distributed Caching:**
- **Chosen**: In-memory caching
- **Rationale**: Simpler implementation, no additional infrastructure
- **Trade-off**: Cache not shared across multiple instances

### Possible Enhancements

**Short-term (Phase 2):**
1. **Redis Integration**: Distributed caching for multi-instance deployments
2. **Async Document Processing**: Background job queue (Celery/RQ)
3. **Advanced Re-ranking**: Cross-encoder models for better retrieval
4. **Multi-language Support**: Language detection and appropriate models
5. **Document Versioning**: Track and manage document updates

**Medium-term (Phase 3):**
1. **Microservices Architecture**: Separate services for ingestion, retrieval, generation
2. **Kubernetes Deployment**: Container orchestration for scaling
3. **Advanced Analytics**: User behavior tracking and query optimization
4. **Hybrid Search**: Combine keyword and semantic search
5. **Fine-tuned Models**: Custom models trained on domain-specific data

**Long-term (Phase 4):**
1. **Multi-modal RAG**: Support for images, tables, charts
2. **Federated Learning**: Privacy-preserving model improvements
3. **Graph-based RAG**: Knowledge graph integration for better reasoning
4. **Active Learning**: User feedback loop for continuous improvement
5. **Multi-tenant Architecture**: Support for multiple organizations

### Performance Considerations

**Current Bottlenecks:**
1. **LLM Generation**: 2-4 seconds per query (largest bottleneck)
2. **Embedding Generation**: 50-100ms per text (batching helps)
3. **Vector Search**: 100-500ms for large collections

**Optimization Priorities:**
1. Implement aggressive query result caching (60% hit rate target)
2. Use smaller, faster models for simple queries
3. Pre-compute embeddings during document ingestion
4. Optimize chunk size for balance between context and speed

### Security Hardening Roadmap

**Immediate:**
- Implement rate limiting per user
- Add input sanitization for all user inputs
- Enable HTTPS with proper certificates
- Set security headers on all responses

**Short-term:**
- Add audit logging for all document operations
- Implement file content validation (not just extension)
- Add CAPTCHA for public-facing instances
- Implement IP-based rate limiting

**Long-term:**
- Add encryption at rest for sensitive documents
- Implement advanced threat detection
- Add compliance features (GDPR, HIPAA)
- Implement zero-trust security model

---

## Conclusion

This architecture provides a solid foundation for a production-ready RAG application that prioritizes:

1. **Privacy**: All processing occurs on the server with configurable security controls
2. **Performance**: Optimized for sub-5-second query responses
3. **Scalability**: Handles 7,500+ documents with room for growth
4. **Maintainability**: Clear separation of concerns and modular design
5. **Security**: Multiple layers of protection for data and users

The layered architecture allows for independent evolution of components, while the local-first design ensures complete data privacy. The system is production-ready for deployment on a single server and has a clear path for horizontal scaling when needed.