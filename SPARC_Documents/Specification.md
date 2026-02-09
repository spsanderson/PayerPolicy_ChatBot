Excellent! I now have all the information needed to create comprehensive SPARC documentation for your local RAG application. Let me build this out for you.

---

# SPARC Documentation: Web-Based RAG Application with Ollama

## **S - SPECIFICATION**

### **Project Overview**

#### **Project Goal**
Develop a web-based, privacy-focused Retrieval-Augmented Generation (RAG) application that enables users to perform intelligent question-answering against a large knowledge base of documents (7,500+) through a REST API. The system will use Ollama for LLM inference (either locally or remotely hosted) and provide transparent source attribution through a web-based chat interface accessible over the internet.

#### **Context and Background**
RAG is a technique that enhances large language model accuracy by retrieving relevant information from external knowledge sources before generating responses . By combining retrieval-based and generation-based methods, RAG systems first retrieve relevant documents from a knowledge base and then use that information to generate contextually accurate answers .

#### **Target Audience**

**Primary Users:**
- Knowledge workers requiring quick access to organizational documentation
- Researchers needing to query large document collections
- Teams requiring private, cloud-hosted or web-accessible document Q&A capabilities

**User Personas:**

1. **Sarah - Research Analyst**
   - Needs to quickly find specific information across thousands of reports
   - Values accuracy and source transparency
   - Technical comfort: Medium

2. **Mike - Compliance Officer**
   - Requires verifiable answers with clear source attribution
   - Handles sensitive documents requiring secure server-side processing
   - Technical comfort: Low-Medium

3. **Dev Team - Internal Users**
   - Need to query technical documentation and specifications
   - Value speed and precision
   - Technical comfort: High

---

### **Functional Requirements**

#### **FR1: Document Ingestion and Processing**
- **FR1.1**: Support PDF document upload and processing
- **FR1.2**: Extract text content from documents while preserving structure
- **FR1.3**: Handle batch uploads of multiple documents
- **FR1.4**: Process and store document metadata (filename, upload date, size, type)
- **FR1.5**: Generate unique document identifiers for tracking

#### **FR2: Vector Embedding and Storage**
- **FR2.1**: Generate embeddings using nomic-embed-text model via Ollama
- **FR2.2**: Store embeddings in local vector database
- **FR2.3**: Chunk documents intelligently (respecting paragraph/section boundaries)
- **FR2.4**: Maintain mapping between chunks and source documents
- **FR2.5**: Support incremental indexing of new documents

#### **FR3: Query Processing and Retrieval**
- **FR3.1**: Accept natural language queries through chat interface
- **FR3.2**: Generate query embeddings using the same nomic-embed-text model
- **FR3.3**: Perform semantic similarity search across vector database
- **FR3.4**: Retrieve top-k most relevant document chunks (configurable, default k=5)
- **FR3.5**: Re-rank results based on relevance scores

#### **FR4: Answer Generation**
- **FR4.1**: Construct prompts combining user query and retrieved context
- **FR4.2**: Generate responses using Ollama-hosted LLM
- **FR4.3**: Include source citations in generated answers
- **FR4.4**: Stream responses to UI for better user experience
- **FR4.5**: Handle cases where no relevant documents are found

#### **FR5: Web User Interface**
- **FR5.1**: Provide chat interface for question input and answer display
- **FR5.2**: Display source documents panel showing retrieved chunks
- **FR5.3**: Highlight relevant passages in source documents
- **FR5.4**: Show document metadata (filename, page numbers, relevance scores)
- **FR5.5**: Allow users to click through to view full source documents
- **FR5.6**: Provide document upload interface (only to developers)
- **FR5.7**: Display indexing progress and status
- **FR5.8**: Show chat history

#### **FR6: Document Management**
- **FR6.1**: List all indexed documents
- **FR6.2**: Allow deletion of documents from knowledge base
- **FR6.3**: Show indexing status for each document
- **FR6.4**: Provide search/filter functionality for document list

---

### **Non-Functional Requirements**

#### **NFR1: Performance**
- **NFR1.1**: Query response time < 5 seconds for 95th percentile
- **NFR1.2**: Document indexing rate: minimum 10 documents/minute
- **NFR1.3**: Support concurrent queries from up to 10 users
- **NFR1.4**: Vector search latency < 500ms for 7,500+ documents
- **Importance**: Critical for user satisfaction and productivity

#### **NFR2: Scalability**
- **NFR2.1**: Handle knowledge base of 7,500+ documents
- **NFR2.2**: Support documents up to 100MB each
- **NFR2.3**: Total storage capacity: 50GB+ for vectors and documents
- **NFR2.4**: Graceful degradation under heavy load
- **Importance**: Ensures system remains functional as document collection grows

#### **NFR3: Privacy and Security**
- **NFR3.1**: All processing occurs on the application server (supporting both self-hosted and remote Ollama instances)
- **NFR3.2**: Document data remains secure on the application server
- **NFR3.3**: Secure file upload validation (file type, size limits)
- **NFR3.4**: Access control for document upload/deletion operations
- **Importance**: Essential for handling sensitive organizational data

#### **NFR4: Reliability**
- **NFR4.1**: System uptime: 99% during business hours
- **NFR4.2**: Graceful error handling with user-friendly messages
- **NFR4.3**: Automatic recovery from Ollama service interruptions
- **NFR4.4**: Data persistence across system restarts
- **Importance**: Ensures consistent availability for users

#### **NFR5: Maintainability**
- **NFR5.1**: Modular architecture with clear separation of concerns
- **NFR5.2**: Comprehensive logging for debugging
- **NFR5.3**: Configuration via environment variables or config files
- **NFR5.4**: Clear documentation for deployment and maintenance
- **Importance**: Reduces long-term operational costs

#### **NFR6: Usability**
- **NFR6.1**: Intuitive interface requiring minimal training
- **NFR6.2**: Clear visual feedback for all operations
- **NFR6.3**: Responsive design for different screen sizes
- **NFR6.4**: Accessibility compliance (WCAG 2.1 Level AA)
- **Importance**: Ensures adoption across diverse user base

---

### **User Scenarios and User Flows**

#### **Scenario 1: First-Time Document Upload**

**Actor**: Sarah (Research Analyst)

**Goal**: Index a collection of research reports for future querying

**Flow**: (Comment: The use case does not align with what we are trying to achieve)
1. Sarah navigates to the web application
2. Clicks "Upload Documents" button
3. Selects 50 PDF research reports from her local drive
4. System validates file types and sizes
5. Upload progress bar displays
6. System begins processing documents in background
7. Indexing status updates in real-time
8. Notification appears when indexing completes
9. Documents appear in "Indexed Documents" list

**Decision Points**:
- If invalid file type detected → Show error, allow re-selection
- If file too large → Show warning, skip file, continue with others
- If Ollama service unavailable → Queue documents, retry automatically

---

#### **Scenario 2: Asking a Question**

**Actor**: Mike (Compliance Officer)

**Goal**: Find specific compliance requirements across policy documents

**Flow**:
1. Mike opens the chat interface
2. Types question: "What are the data retention requirements for customer records?"
3. Clicks "Send" or presses Enter
4. System shows "Searching..." indicator
5. Retrieved source documents appear in right panel
6. Answer streams into chat window with inline citations
7. Mike clicks on citation  to view source passage
8. Source document highlights relevant section
9. Mike asks follow-up question in same conversation

**Decision Points**:
- If no relevant documents found → Display message suggesting query refinement
- If confidence score low → Include disclaimer in response
- If Ollama generates incomplete response → Show retry option

---

#### **Scenario 3: Managing Document Collection**

**Actor**: Dev Team Member

**Goal**: Remove outdated documentation and add updated versions

**Flow**:
1. User navigates to "Document Management" section
2. Filters documents by date or filename
3. Selects outdated documents using checkboxes
4. Clicks "Delete Selected" button
5. Confirmation dialog appears
6. User confirms deletion
7. System removes documents and associated vectors
8. User uploads new versions via upload interface
9. System re-indexes new documents

---

### **UI/UX Considerations**

#### **Design Principles**
- **Clarity**: Clear visual hierarchy, obvious action buttons
- **Transparency**: Always show which sources inform answers
- **Responsiveness**: Immediate feedback for all user actions
- **Simplicity**: Minimal learning curve, intuitive navigation

#### **Layout Structure**

```
┌─────────────────────────────────────────────────────────┐
│  Header: Logo | Document Management | Settings          │
├────────────────────────────────|────────────────────────┤
│                                │                        │
│      Chat Interface            │ Source Documents Panel │
│     ┌────────────────────┐     │┌──────────────────────┐│
│     │ User: Question     │     ││Document 1 Score: 0.9 ││
│     │ Bot: Answer [1][2] │     ││ "<relevant passage>" ││
│     │                    │     ││                      ││
│     │                    │     ││Document 2 Score: 0.85││
│     └────────────────────┘     ││ "<relevant passage>" ││
│     [Type your question...]    │└──────────────────────┘│
│     [History]                  │                        │
└────────────────────────────────|────────────────────────┘
```

#### **Accessibility Standards**
- WCAG 2.1 Level AA compliance
- Keyboard navigation support
- Screen reader compatibility
- Sufficient color contrast ratios (4.5:1 minimum)
- Alt text for all images and icons

---

### **File Structure Proposal**

```
rag-ollama-app/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── config/
│   ├── __init__.py
│   ├── settings.py          # Configuration management
│   └── logging_config.py    # Logging setup
├── src/
│   ├── __init__.py
│   ├── app.py               # Flask application entry point
│   ├── document_processor/
│   │   ├── __init__.py
│   │   ├── pdf_processor.py
│   │   └── chunker.py       # Document chunking logic
│   ├── embeddings/
│   │   ├── __init__.py
│   │   ├── embedding_generator.py
│   │   └── ollama_client.py
│   ├── vector_store/
│   │   ├── __init__.py
│   │   ├── vector_db.py     # Vector database interface
│   │   └── retriever.py     # Retrieval logic
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── ollama_llm.py    # LLM interaction
│   │   └── prompt_templates.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py        # Flask routes
│   │   └── schemas.py       # Request/response schemas
│   └── utils/
│       ├── __init__.py
│       ├── file_validator.py
│       └── error_handlers.py
├── static/
│   ├── css/
│   │   └── styles.css
│   ├── js/
│   │   ├── chat.js
│   │   ├── upload.js
│   │   └── document_manager.js
│   └── images/
├── templates/
│   ├── base.html
│   ├── index.html           # Main chat interface
│   ├── upload.html
│   └── documents.html       # Document management
├── data/
│   ├── uploads/             # Temporary upload storage
│   ├── processed/           # Processed documents
│   └── vector_db/           # Vector database files
├── tests/
│   ├── __init__.py
│   ├── test_document_processor.py
│   ├── test_embeddings.py
│   ├── test_vector_store.py
│   └── test_api.py
└── docs/
    ├── SPARC.md             # This document
    ├── DEPLOYMENT.md
    └── API.md
```

---

### **Assumptions**

1. **Ollama Installation**: Ollama is pre-installed and configured on the local server (If this is the case then should we remove the api/ folder from above?)
   - *Justification*: Required for local LLM inference
   - *Impact*: Deployment documentation must include Ollama setup instructions

2. **Document Quality**: Uploaded documents contain extractable text (not scanned images)
   - *Justification*: OCR adds significant complexity
   - *Impact*: May need OCR capability in future iterations

3. **Single Language**: All documents are in English
   - *Justification*: Simplifies initial implementation
   - *Impact*: Multi-language support can be added later

4. **Network Availability**: Local server has stable network for users to access web UI
   - *Justification*: Standard deployment assumption
   - *Impact*: No offline mode required

5. **Hardware Resources**: Server has sufficient RAM (16GB+) and storage (100GB+)
   - *Justification*: Required for vector database and LLM operations
   - *Impact*: Hardware requirements must be documented

6. **User Authentication**: Basic authentication is sufficient (not enterprise SSO) (Or microsoft windows authentication?)
   - *Justification*: Reduces initial complexity
   - *Impact*: Can integrate with existing auth systems later

7. **Document Updates**: Documents are relatively static (not frequently updated)
   - *Justification*: Simplifies versioning and re-indexing logic
   - *Impact*: Version control can be added if needed

---

### **Actors**

#### **Primary Actors**

1. **End Users**
   - Role: Query the knowledge base through chat interface
   - Permissions: Read access to indexed documents, submit queries
   - Technical Level: Low to Medium

2. **Document Administrators**
   - Role: Upload, manage, and delete documents
   - Permissions: Full CRUD operations on documents
   - Technical Level: Medium

3. **System Administrators**
   - Role: Deploy, configure, and maintain the application
   - Permissions: Full system access, configuration management
   - Technical Level: High

#### **System Actors**

1. **Ollama Service**
   - Role: Provides LLM inference and embedding generation
   - Interface: HTTP API (configurable via ${OLLAMA_BASE_URL} environment variable)

2. **Vector Database**
   - Role: Stores and retrieves document embeddings
   - Interface: Python library API

3. **File System**
   - Role: Stores uploaded documents and processed data
   - Interface: OS file operations

---

### **Resources**

#### **Software Requirements**
- Python 3.10+
- Ollama (with nomic-embed-text and llama2/mistral models)
- Flask 3.0+
- Vector database library (ChromaDB or FAISS)
- PyPDF2 or pdfplumber for PDF processing
- openpyxl or pandas for Excel processing
- langchain or llamaindex (optional, for RAG orchestration)

#### **Hardware Requirements**
- CPU: 8+ cores recommended
- RAM: 16GB minimum, 32GB recommended
- Storage: 100GB+ SSD
- GPU: Optional but recommended for faster inference

#### **Personnel**
- 2 Developer

#### **Development Tools**
- Git for version control
- VS Code or PyCharm
- Postman for API testing (Do we need this, if so why?)
- Docker for containerization (optional)

---

### **Constraints**

#### **Technical Constraints**
- **TC1**: Must use Ollama (no external API calls)
- **TC2**: All processing must occur on local server
- **TC3**: Vector database must support web-based deployment
- **TC4**: Limited to document types with text extraction capabilities

#### **Performance Constraints**
- **PC1**: Response time limited by local hardware capabilities
- **PC2**: Concurrent user limit based on server resources
- **PC3**: Document processing speed limited by CPU/GPU availability

#### **Legal/Compliance Constraints**
- **LC1**: Must maintain data privacy (no external data transmission)
- **LC2**: Document access must be auditable
- **LC3**: Must comply with organizational data retention policies

#### **Budgetary Constraints**
- **BC1**: No licensing costs for external APIs
- **BC2**: Open-source software preferred
- **BC3**: Hardware costs limited to existing server infrastructure

---

### **Reflection and Justification**

#### **Why RAG Architecture?**
RAG combines the benefits of retrieval-based systems (factual accuracy, source attribution) with generative models (natural language understanding, contextual responses) . This is ideal for document Q&A where accuracy and transparency are critical.

#### **Why Ollama?**
- **Privacy**: All data remains local, critical for sensitive documents
- **Cost**: No per-token API costs
- **Control**: Full control over model selection and configuration
- **Latency**: Eliminates network round-trips to external services

#### **Why nomic-embed-text?**
- Optimized for retrieval tasks
- Efficient performance on CPU
- Good balance of quality and speed
- Well-supported by Ollama

#### **Potential Challenges and Mitigation**

**Challenge 1: Large Document Collection Performance**
- *Risk*: Slow retrieval with 7,500+ documents
- *Mitigation*: Use efficient vector database with indexing, implement caching, consider hierarchical retrieval

**Challenge 2: Context Window Limitations**
- *Risk*: Retrieved chunks may exceed LLM context window
- *Mitigation*: Implement intelligent chunk selection, summarize long contexts, use models with larger context windows

**Challenge 3: Answer Quality**
- *Risk*: Generated answers may be inaccurate or hallucinated
- *Mitigation*: Implement confidence scoring, show source passages, allow user feedback, use prompt engineering techniques

**Challenge 4: Resource Contention**
- *Risk*: Multiple concurrent users may overwhelm server
- *Mitigation*: Implement request queuing, rate limiting, resource monitoring, graceful degradation

---

## **P - PSEUDOCODE**

### **Core RAG Pipeline**

```
FUNCTION main_rag_pipeline(user_query):
    // Step 1: Generate query embedding
    query_embedding = generate_embedding(user_query)
    
    // Step 2: Retrieve relevant documents
    relevant_chunks = vector_search(query_embedding, top_k=5)
    
    // Step 3: Re-rank results
    ranked_chunks = rerank_by_relevance(relevant_chunks, user_query)
    
    // Step 4: Construct context
    context = build_context_from_chunks(ranked_chunks)
    
    // Step 5: Generate answer
    prompt = create_rag_prompt(user_query, context)
    answer = generate_llm_response(prompt)
    
    // Step 6: Add citations
    cited_answer = add_source_citations(answer, ranked_chunks)
    
    RETURN {
        answer: cited_answer,
        sources: ranked_chunks,
        metadata: {query_time, num_sources, confidence}
    }
END FUNCTION
```

---

### **Document Ingestion Pipeline**

```
FUNCTION ingest_document(file_path, file_type):
    // Step 1: Validate file
    IF NOT validate_file(file_path, file_type):
        RAISE ValidationError("Invalid file type or size")
    
    // Step 2: Extract text
    IF file_type == "pdf":
        text_content = extract_pdf_text(file_path)
    ELSE IF file_type == "excel":
        text_content = extract_excel_text(file_path)
    ELSE:
        RAISE UnsupportedFileTypeError
    
    // Step 3: Create metadata
    metadata = {
        filename: get_filename(file_path),
        upload_date: current_timestamp(),
        file_size: get_file_size(file_path),
        file_type: file_type,
        document_id: generate_uuid()
    }
    
    // Step 4: Chunk document
    chunks = chunk_document(text_content, chunk_size=500, overlap=50)
    
    // Step 5: Generate embeddings for each chunk
    FOR EACH chunk IN chunks:
        chunk.embedding = generate_embedding(chunk.text)
        chunk.metadata = metadata
        chunk.chunk_id = generate_chunk_id()
    
    // Step 6: Store in vector database
    vector_db.add_documents(chunks)
    
    // Step 7: Store original document
    save_document(file_path, metadata.document_id)
    
    RETURN metadata.document_id
END FUNCTION
```

---

### **Embedding Generation**

```
FUNCTION generate_embedding(text):
    // Step 1: Prepare request to Ollama
    request = {
        model: "nomic-embed-text",
        prompt: text
    }
    
    // Step 2: Call Ollama API
    TRY:
        response = http_post("${OLLAMA_BASE_URL}/api/embeddings", request)
        embedding = response.embedding
    CATCH OllamaConnectionError:
        LOG_ERROR("Ollama service unavailable")
        RETRY with exponential_backoff(max_retries=3)
    
    // Step 3: Normalize embedding (optional)
    normalized_embedding = normalize_vector(embedding)
    
    RETURN normalized_embedding
END FUNCTION
```

---

### **Vector Search and Retrieval**

```
FUNCTION vector_search(query_embedding, top_k=5):
    // Step 1: Perform similarity search
    results = vector_db.similarity_search(
        query_vector=query_embedding,
        k=top_k,
        metric="cosine"
    )
    
    // Step 2: Filter by minimum similarity threshold
    filtered_results = []
    FOR EACH result IN results:
        IF result.similarity_score >= 0.7:
            filtered_results.append(result)
    
    // Step 3: Enrich with metadata
    enriched_results = []
    FOR EACH result IN filtered_results:
        enriched_result = {
            text: result.text,
            score: result.similarity_score,
            document_id: result.metadata.document_id,
            filename: result.metadata.filename,
            chunk_id: result.chunk_id
        }
        enriched_results.append(enriched_result)
    
    RETURN enriched_results
END FUNCTION
```

---

### **Document Chunking Strategy**

```
FUNCTION chunk_document(text, chunk_size=500, overlap=50):
    chunks = []
    
    // Step 1: Split by paragraphs first
    paragraphs = split_by_paragraphs(text)
    
    current_chunk = ""
    current_length = 0
    
    // Step 2: Build chunks respecting paragraph boundaries
    FOR EACH paragraph IN paragraphs:
        paragraph_length = count_tokens(paragraph)
        
        IF current_length + paragraph_length <= chunk_size:
            current_chunk += paragraph + "\n"
            current_length += paragraph_length
        ELSE:
            // Save current chunk
            IF current_chunk:
                chunks.append(create_chunk(current_chunk))
            
            // Start new chunk with overlap
            IF paragraph_length > chunk_size:
                // Split large paragraph
                sub_chunks = split_large_paragraph(paragraph, chunk_size, overlap)
                chunks.extend(sub_chunks)
                current_chunk = ""
                current_length = 0
            ELSE:
                // Add overlap from previous chunk
                overlap_text = get_last_n_tokens(current_chunk, overlap)
                current_chunk = overlap_text + paragraph
                current_length = count_tokens(current_chunk)
    
    // Add final chunk
    IF current_chunk:
        chunks.append(create_chunk(current_chunk))
    
    RETURN chunks
END FUNCTION
```

---

### **LLM Response Generation**

```
FUNCTION generate_llm_response(prompt):
    // Step 1: Prepare request
    request = {
        model: "llama2",  // or mistral, or other model
        prompt: prompt,
        stream: true,
        options: {
            temperature: 0.7,
            top_p: 0.9,
            max_tokens: 1000
        }
    }
    
    // Step 2: Stream response
    response_text = ""
    TRY:
        stream = http_post_stream("${OLLAMA_BASE_URL}/api/generate", request)
        
        FOR EACH chunk IN stream:
            token = chunk.response
            response_text += token
            yield token  // Stream to frontend
            
    CATCH OllamaError as e:
        LOG_ERROR("LLM generation failed", e)
        RETURN "I apologize, but I encountered an error generating a response."
    
    RETURN response_text
END FUNCTION
```

---

### **Prompt Construction**

```
FUNCTION create_rag_prompt(user_query, context_chunks):
    // Build context section
    context_text = ""
    FOR i, chunk IN enumerate(context_chunks):
        context_text += f"[{i+1}] {chunk.text}\n\n"
    
    // Construct full prompt
    prompt = f"""You are a helpful assistant answering questions based on provided documents.

Context Information:
{context_text}

User Question: {user_query}

Instructions:
- Answer the question using ONLY the information from the context above
- Cite sources using [1], [2], etc. after each claim
- If the context doesn't contain enough information, say so
- Be concise but complete
- Do not make up information

Answer:"""
    
    RETURN prompt
END FUNCTION
```

---

### **Citation Addition**

```
FUNCTION add_source_citations(answer_text, source_chunks):
    // This is a simplified version - actual implementation would be more sophisticated
    
    cited_answer = answer_text
    citations = []
    
    FOR i, chunk IN enumerate(source_chunks):
        citation_marker = f"[{i+1}]"
        
        // Check if citation already exists in answer
        IF citation_marker NOT IN cited_answer:
            // Try to find relevant sentences to add citation
            sentences = split_into_sentences(cited_answer)
            FOR sentence IN sentences:
                IF has_semantic_overlap(sentence, chunk.text):
                    cited_answer = cited_answer.replace(
                        sentence,
                        sentence + f" {citation_marker}"
                    )
                    BREAK
        
        // Build citation object
        citation = {
            number: i+1,
            filename: chunk.filename,
            text_snippet: chunk.text[:200],
            document_id: chunk.document_id
        }
        citations.append(citation)
    
    RETURN {
        answer: cited_answer,
        citations: citations
    }
END FUNCTION
```

---

### **Flask API Routes**

```
// Chat endpoint
ROUTE POST /api/chat:
    FUNCTION handle_chat_request(request):
        user_query = request.json.get("query")
        conversation_id = request.json.get("conversation_id", generate_uuid())
        
        // Validate input
        IF NOT user_query OR len(user_query) < 3:
            RETURN error_response("Query too short", 400)
        
        // Process query
        TRY:
            result = main_rag_pipeline(user_query)
            
            // Log conversation
            log_conversation(conversation_id, user_query, result)
            
            RETURN json_response({
                conversation_id: conversation_id,
                answer: result.answer,
                sources: result.sources,
                metadata: result.metadata
            })
        CATCH Exception as e:
            LOG_ERROR("Chat request failed", e)
            RETURN error_response("Internal server error", 500)
    END FUNCTION

// Document upload endpoint
ROUTE POST /api/upload:
    FUNCTION handle_upload_request(request):
        files = request.files.getlist("documents")
        
        IF NOT files:
            RETURN error_response("No files provided", 400)
        
        results = []
        FOR file IN files:
            TRY:
                // Save temporarily
                temp_path = save_temp_file(file)
                
                // Validate and process
                file_type = detect_file_type(file.filename)
                document_id = ingest_document(temp_path, file_type)
                
                results.append({
                    filename: file.filename,
                    document_id: document_id,
                    status: "success"
                })
            CATCH Exception as e:
                results.append({
                    filename: file.filename,
                    status: "failed",
                    error: str(e)
                })
        
        RETURN json_response({
            uploaded: len([r for r in results if r.status == "success"]),
            failed: len([r for r in results if r.status == "failed"]),
            details: results
        })
    END FUNCTION

// Document list endpoint
ROUTE GET /api/documents:
    FUNCTION handle_list_documents(request):
        page = request.args.get("page", 1)
        per_page = request.args.get("per_page", 50)
        
        documents = vector_db.list_documents(page, per_page)
        total_count = vector_db.count_documents()
        
        RETURN json_response({
            documents: documents,
            total: total_count,
            page: page,
            per_page: per_page
        })
    END FUNCTION

// Document deletion endpoint
ROUTE DELETE /api/documents/<document_id>:
    FUNCTION handle_delete_document(document_id):
        TRY:
            // Remove from vector database
            vector_db.delete_document(document_id)
            
            // Remove original file
            delete_stored_document(document_id)
            
            RETURN json_response({
                message: "Document deleted successfully",
                document_id: document_id
            })
        CATCH DocumentNotFoundError:
            RETURN error_response("Document not found", 404)
    END FUNCTION
```

---

### **Frontend JavaScript Logic**

```javascript
// Chat functionality
FUNCTION sendMessage():
    userQuery = getInputValue("chat-input")
    
    IF userQuery.trim() == "":
        RETURN
    
    // Display user message
    appendMessage("user", userQuery)
    clearInput("chat-input")
    
    // Show loading indicator
    showLoadingIndicator()
    
    // Send request to backend
    TRY:
        response = await fetch("/api/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                query: userQuery,
                conversation_id: currentConversationId
            })
        })
        
        data = await response.json()
        
        // Display bot response
        appendMessage("bot", data.answer)
        
        // Display sources in side panel
        displaySources(data.sources)
        
        // Hide loading indicator
        hideLoadingIndicator()
        
    CATCH error:
        showError("Failed to get response. Please try again.")
        hideLoadingIndicator()
END FUNCTION

```javascript
// Document upload functionality (continued)
FUNCTION uploadDocuments():
    files = getSelectedFiles("file-input")
    
    IF files.length == 0:
        showError("Please select files to upload")
        RETURN
    
    formData = new FormData()
    FOR EACH file IN files:
        formData.append("documents", file)
    
    // Show progress bar
    showProgressBar()
    
    TRY:
        response = await fetch("/api/upload", {
            method: "POST",
            body: formData
        })
        
        data = await response.json()
        
        // Update UI with results
        showUploadResults(data)
        
        // Refresh document list
        refreshDocumentList()
        
        // Hide progress bar
        hideProgressBar()
        
    CATCH error:
        showError("Upload failed. Please try again.")
        hideProgressBar()
END FUNCTION

// Display sources in side panel
FUNCTION displaySources(sources):
    sourcesContainer = getElementById("sources-panel")
    sourcesContainer.innerHTML = ""
    
    FOR EACH source IN sources:
        sourceCard = createSourceCard(source)
        sourcesContainer.appendChild(sourceCard)
END FUNCTION

FUNCTION createSourceCard(source):
    card = createElement("div", class="source-card")
    
    // Add filename and score
    header = createElement("div", class="source-header")
    header.innerHTML = `
        <strong>${source.filename}</strong>
        <span class="score">Relevance: ${(source.score * 100).toFixed(1)}%</span>
    `
    
    // Add text snippet
    snippet = createElement("div", class="source-snippet")
    snippet.textContent = source.text
    
    // Add click handler to view full document
    card.onclick = () => viewFullDocument(source.document_id)
    
    card.appendChild(header)
    card.appendChild(snippet)
    
    RETURN card
END FUNCTION
```

---

## **A - ARCHITECTURE**

### **System Architecture Overview**

The RAG application follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                     Presentation Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Chat UI      │  │ Upload UI    │  │ Doc Mgmt UI  │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
└─────────┼──────────────────┼──────────────────┼─────────────┘
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼─────────────┐
│         │        API Layer (Flask Routes)     │             │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌───────▼──────┐      │
│  │ /api/chat    │  │ /api/upload  │  │ /api/docs    │      │
│  └──────┬───────┘  └──────┬───────┘  └───────┬──────┘      │
└─────────┼──────────────────┼──────────────────┼─────────────┘
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼─────────────┐
│         │         Business Logic Layer        │             │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌───────▼──────┐      │
│  │ RAG Pipeline │  │ Doc Processor│  │ Doc Manager  │      │
│  └──────┬───────┘  └──────┬───────┘  └───────┬──────┘      │
└─────────┼──────────────────┼──────────────────┼─────────────┘
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼─────────────┐
│         │         Data Access Layer           │             │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌───────▼──────┐      │
│  │ Vector Store │  │ Embedding Gen│  │ File Storage │      │
│  └──────┬───────┘  └──────┬───────┘  └───────┬──────┘      │
└─────────┼──────────────────┼──────────────────┼─────────────┘
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼─────────────┐
│         │      External Services Layer        │             │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌───────▼──────┐      │
│  │ ChromaDB     │  │ Ollama API   │  │ File System  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

### **Component Descriptions**

#### **1. Presentation Layer**

**Chat UI Component**
- Renders chat interface with message history
- Handles user input and displays streaming responses
- Shows typing indicators and error states
- Technologies: HTML5, CSS3, JavaScript (vanilla or React)

**Upload UI Component**
- File selection interface with drag-and-drop support
- Progress indicators for upload and processing
- Validation feedback for file types and sizes
- Technologies: HTML5, CSS3, JavaScript

**Document Management UI Component**
- Lists all indexed documents with metadata
- Provides search/filter functionality
- Handles document deletion with confirmation
- Technologies: HTML5, CSS3, JavaScript

---

#### **2. API Layer (Flask)**

**Flask Application (`app.py`)**
- Initializes Flask app and configurations
- Registers blueprints for different route groups
- Sets up middleware (CORS, logging, error handling)
- Manages application lifecycle

**Route Handlers (`api/routes.py`)**
- `/api/chat` - POST: Handles chat queries
- `/api/upload` - POST: Handles document uploads
- `/api/documents` - GET: Lists documents
- `/api/documents/<id>` - DELETE: Removes documents
- `/api/documents/<id>` - GET: Retrieves document details
- `/api/health` - GET: Health check endpoint

**Request/Response Schemas (`api/schemas.py`)**
- Validates incoming requests
- Serializes outgoing responses
- Ensures data consistency
- Technologies: Pydantic or marshmallow

---

#### **3. Business Logic Layer**

**RAG Pipeline Module (`rag_pipeline.py`)**
- Orchestrates the complete RAG workflow
- Coordinates between retrieval and generation
- Implements retry logic and error handling
- Manages conversation context

**Document Processor Module (`document_processor/`)**
- **PDF Processor**: Extracts text from PDFs using PyPDF2 or pdfplumber
- **Excel Processor**: Extracts text from Excel files using openpyxl
- **Text Extractor**: Common text extraction utilities
- **Chunker**: Implements intelligent document chunking

**Document Manager Module (`document_manager.py`)**
- CRUD operations for documents
- Metadata management
- Document versioning (future)
- Batch operations

---

#### **4. Data Access Layer**

**Vector Store Module (`vector_store/`)**
- **Vector DB Interface**: Abstract interface for vector operations
- **Retriever**: Implements similarity search and ranking
- Handles connection pooling and caching
- Technologies: ChromaDB (supports both local and cloud deployment)

**Embedding Generator Module (`embeddings/`)**
- **Ollama Client**: Communicates with Ollama API
- **Embedding Generator**: Generates embeddings for text
- Implements batching for efficiency
- Handles rate limiting and retries

**LLM Module (`llm/`)**
- **Ollama LLM**: Interfaces with Ollama for text generation
- **Prompt Templates**: Manages prompt construction
- Implements streaming responses
- Handles context window management

---

#### **5. External Services**

**ChromaDB**
- Persistent vector database
- Stores document embeddings and metadata
- Provides similarity search capabilities
- Flexible deployment options (local, cloud, containerized)

**Ollama Service**
- Runs locally on port 11434
- Provides embedding generation (nomic-embed-text)
- Provides text generation (llama2, mistral, etc.)
- Manages model loading and inference

**File System**
- Stores uploaded documents
- Maintains processed document cache
- Stores application logs
- Organized directory structure

---

### **Data Flow Diagrams**

#### **Query Processing Flow**

```
User Query
    │
    ▼
┌─────────────────┐
│  Flask Route    │
│  /api/chat      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  RAG Pipeline   │
│  Orchestrator   │
└────────┬────────┘
         │
         ├──────────────────────┐
         │                      │
         ▼                      ▼
┌─────────────────┐    ┌─────────────────┐
│ Embedding Gen   │    │ Vector Store    │
│ (Query)         │───▶│ Similarity      │
└─────────────────┘    │ Search          │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Retrieved       │
                       │ Chunks (Top-K)  │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Prompt          │
                       │ Construction    │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Ollama LLM      │
                       │ Generation      │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Citation        │
                       │ Addition        │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Response to     │
                       │ Frontend        │
                       └─────────────────┘
```

---

#### **Document Ingestion Flow**

```
File Upload
    │
    ▼
┌─────────────────┐
│  Flask Route    │
│  /api/upload    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  File           │
│  Validation     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Document       │
│  Processor      │
│  (PDF/Excel)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Text           │
│  Extraction     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Document       │
│  Chunking       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Embedding      │
│  Generation     │
│  (Batch)        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Vector Store   │
│  Insertion      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  File Storage   │
│  (Original)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Success        │
│  Response       │
└─────────────────┘
```

---

### **Database Schema**

#### **Vector Database (ChromaDB)**

**Collections Structure:**

```
collection: "document_chunks"
├── id: string (UUID)
├── embedding: vector[768]  # nomic-embed-text dimension
├── document: string (chunk text)
└── metadata: {
    ├── document_id: string
    ├── filename: string
    ├── chunk_index: integer
    ├── upload_date: timestamp
    ├── file_type: string
    ├── file_size: integer
    └── page_number: integer (for PDFs)
}
```

#### **Metadata Store (SQLite - Optional)**

```sql
CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'processing',
    chunk_count INTEGER,
    file_path TEXT
);

CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP
);

CREATE TABLE messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT,
    role TEXT CHECK(role IN ('user', 'assistant')),
    content TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sources TEXT,  -- JSON array of source document IDs
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
);
```

---

### **Technology Stack Summary**

**Backend:**
- Python 3.10+
- Flask 3.0+ (web framework)
- ChromaDB (vector database)
- PyPDF2 or pdfplumber (PDF processing)
- openpyxl (Excel processing)
- requests (HTTP client for Ollama)

**Frontend:**
- HTML5, CSS3
- JavaScript (ES6+)
- Optional: React or Vue.js for more complex UI

**Infrastructure:**
- Ollama (local LLM server)
- SQLite (optional metadata storage)
- Nginx (optional reverse proxy)

**Development Tools:**
- Git (version control)
- pytest (testing)
- black (code formatting)
- pylint (linting)

---

### **Security Architecture**

**Input Validation:**
- File type whitelist (PDF, Excel only)
- File size limits (100MB max)
- Query length limits
- SQL injection prevention (parameterized queries)

**Authentication & Authorization:**
- Basic HTTP authentication (initial implementation)
- Session management
- Role-based access control (admin vs. user)

**Data Protection:**
- All data stored securely on the server
- Configurable external service endpoints (Ollama can be local or remote)
- Secure file upload handling
- Input sanitization

**API Security for Web Deployment:**
- JWT-based authentication
- API key authentication for service-to-service calls
- CORS configuration for cross-origin requests
- Rate limiting per IP address
- HTTPS/TLS encryption in production

**Error Handling:**
- Graceful degradation
- User-friendly error messages
- Detailed logging for debugging
- No sensitive information in error responses

---

### **Environment Configuration**

**Required Environment Variables:**

```bash
# API Configuration
API_BASE_URL=https://api.example.com          # Base URL for API endpoints
API_HOST=api.example.com                       # API hostname for CORS

# Ollama Configuration
OLLAMA_BASE_URL=https://ollama.example.com     # Remote Ollama instance
# Or: http://localhost:11434 for local development

# CORS Configuration (for web clients)
CORS_ORIGINS=https://app.example.com,https://www.example.com
CORS_ALLOW_CREDENTIALS=true

# Security
JWT_SECRET=your-jwt-secret-key-min-32-chars
API_KEY=your-api-key-for-service-auth
ENABLE_RATE_LIMITING=true
ENABLE_HTTPS=true

# Application
SECRET_KEY=your-secret-key-min-32-chars
ENVIRONMENT=production
DEBUG=False
```

**CORS Configuration Requirements:**

```python
# Flask CORS middleware configuration
from flask_cors import CORS

CORS(app, resources={
    r"/api/*": {
        "origins": os.getenv("CORS_ORIGINS", "*").split(","),
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})
```

**Cloud Deployment Options:**

1. **AWS**: EC2, ECS, Lambda with API Gateway
2. **Azure**: App Service, Container Instances, AKS
3. **GCP**: Cloud Run, Compute Engine, GKE
4. **Docker**: Containerized deployment with docker-compose
5. **Kubernetes**: Scalable orchestration for high availability

---

## **R - REFINEMENT**

### **Performance Optimizations**

#### **1. Embedding Generation Optimization**

**Batching Strategy:**
```python
# Instead of generating embeddings one at a time
for chunk in chunks:
    embedding = generate_embedding(chunk.text)  # Slow

# Batch process for efficiency
batch_size = 32
for i in range(0, len(chunks), batch_size):
    batch = chunks[i:i+batch_size]
    embeddings = generate_embeddings_batch([c.text for c in batch])
```

**Caching:**
- Cache embeddings for frequently accessed queries
- Use LRU cache with configurable size
- Cache key: hash of input text

**Parallel Processing:**
- Use multiprocessing for document ingestion
- Process multiple documents simultaneously
- Limit concurrent processes based on CPU cores

---

#### **2. Vector Search Optimization**

**Indexing Strategy:**
- Use HNSW (Hierarchical Navigable Small World) index for fast approximate search
- Configure index parameters for balance between speed and accuracy
- Rebuild index periodically for optimal performance

**Query Optimization:**
- Pre-filter by metadata before vector search
- Use approximate nearest neighbor (ANN) for large collections
- Implement result caching for common queries

**Hierarchical Retrieval:**
```
Level 1: Coarse retrieval (top 50 candidates)
    │
    ▼
Level 2: Re-ranking with more expensive similarity metric
    │
    ▼
Level 3: Final selection (top 5)
```

---

#### **3. LLM Generation Optimization**

**Context Window Management:**
- Prioritize most relevant chunks
- Summarize long contexts if needed
- Implement sliding window for long documents

**Prompt Optimization:**
- Keep prompts concise
- Use system prompts effectively
- Implement prompt templates for consistency

**Streaming:**
- Stream responses token-by-token to frontend
- Improve perceived performance
- Allow early termination if needed

---

### **Scalability Improvements**

#### **Horizontal Scaling Considerations**

**Load Balancing:**
- Use Nginx or HAProxy for load distribution
- Session affinity for conversation continuity
- Health checks for backend instances

**Database Scaling:**
- Shard vector database by document categories
- Implement read replicas for query-heavy workloads
- Use connection pooling

**Caching Layer:**
- Redis for distributed caching
- Cache query results
- Cache frequently accessed documents

---

#### **Vertical Scaling Optimizations**

**Resource Management:**
- Limit concurrent Ollama requests
- Implement request queuing
- Monitor memory usage and implement cleanup

**GPU Utilization:**
- Use GPU for embedding generation if available
- Batch operations to maximize GPU utilization
- Monitor GPU memory

---

### **Code Quality Improvements**

#### **Error Handling Refinement**

```python
class RAGException(Exception):
    """Base exception for RAG application"""
    pass

class DocumentProcessingError(RAGException):
    """Raised when document processing fails"""
    pass

class EmbeddingGenerationError(RAGException):
    """Raised when embedding generation fails"""
    pass

class VectorSearchError(RAGException):
    """Raised when vector search fails"""
    pass

# Usage with proper error handling
def process_document_with_retry(file_path, max_retries=3):
    for attempt in range(max_retries):
        try:
            return process_document(file_path)
        except DocumentProcessingError as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed to process document after {max_retries} attempts")
                raise
            logger.warning(f"Attempt {attempt + 1} failed, retrying...")
            time.sleep(2 ** attempt)  # Exponential backoff
```

---

#### **Logging Strategy**

```python
import logging
from logging.handlers import RotatingFileHandler

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('logs/app.log', maxBytes=10485760, backupCount=5),
        logging.StreamHandler()
    ]
)

# Log important events
logger.info("Document uploaded", extra={
    "document_id": doc_id,
    "filename": filename,
    "file_size": file_size,
    "user_id": user_id
})

# Log performance metrics
logger.info("Query processed", extra={
    "query_time_ms": elapsed_time * 1000,
    "num_results": len(results),
    "query_length": len(query)
})
```

---

#### **Configuration Management**

```python
# config/settings.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "RAG Ollama App"
    DEBUG: bool = False
    
    # Ollama
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_LLM_MODEL: str = "llama2"
    
    # Vector Database
    VECTOR_DB_PATH: str = "./data/vector_db"
    VECTOR_DB_COLLECTION: str = "document_chunks"
    
    # Document Processing
    MAX_FILE_SIZE_MB: int = 100
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    ALLOWED_FILE_TYPES: list = ["pdf", "xlsx", "xls"]
    
    # RAG Parameters
    TOP_K_RESULTS: int = 5
    SIMILARITY_THRESHOLD: float = 0.7
    MAX_CONTEXT_LENGTH: int = 4000
    
    # Performance
    BATCH_SIZE: int = 32
    MAX_CONCURRENT_REQUESTS: int = 10
    CACHE_SIZE: int = 1000
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

### **Testing Strategy Refinement**

#### **Unit Tests**

```python
# tests/test_document_processor.py
import pytest
from src.document_processor.pdf_processor import PDFProcessor

def test_pdf_text_extraction():
    processor = PDFProcessor()
    text = processor.extract_text("tests/fixtures/sample.pdf")
    assert len(text) > 0
    assert "expected content" in text

def test_pdf_invalid_file():
    processor = PDFProcessor()
    with pytest.raises(DocumentProcessingError):
        processor.extract_text("tests/fixtures/invalid.pdf")

# tests/test_embeddings.py
def test_embedding_generation():
    generator = EmbeddingGenerator()
    text = "This is a test sentence."
    embedding = generator.generate(text)
    assert len(embedding) == 768  # nomic-embed-text dimension
    assert all(isinstance(x, float) for x in embedding)

def test_embedding_batch():
    generator = EmbeddingGenerator()
    texts = ["Text 1", "Text 2", "Text 3"]
    embeddings = generator.generate_batch(texts)
    assert len(embeddings) == 3
    assert all(len(emb) == 768 for emb in embeddings)
```

---

#### **Integration Tests**

```python
# tests/test_rag_pipeline.py
def test_end_to_end_query():
    # Setup: Ingest test document
    doc_id = ingest_document("tests/fixtures/test_doc.pdf", "pdf")
    
    # Execute: Run query
    result = main_rag_pipeline("What is the main topic?")
    
    # Assert: Check response quality
    assert result["answer"] is not None
    assert len(result["sources"]) > 0
    assert result["metadata"]["query_time"] < 5.0
    
    # Cleanup
    delete_document(doc_id)

def test_concurrent_queries():
    import concurrent.futures
    
    queries = ["Query 1", "Query 2", "Query 3"]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(main_rag_pipeline, q) for q in queries]
        results = [f.result() for f in futures]
    
    assert len(results) == 3
    assert all(r["answer"] is not None for r in results)
```

---

#### **Performance Tests**

```python
# tests/test_performance.py
import time

def test_query_response_time():
    start = time.time()
    result = main_rag_pipeline("Test query")
    elapsed = time.time() - start
    
    assert elapsed < 5.0, f"Query took {elapsed}s, expected < 5s"

def test_document_ingestion_rate():
    start = time.time()
    
    for i in range(10):
        ingest_document(f"tests/fixtures/doc_{i}.pdf", "pdf")
    
    elapsed = time.time() - start
    rate = 10 / elapsed
    
    assert rate >= 10, f"Ingestion rate {rate} docs/min, expected >= 10"
```

---

### **User Experience Refinements**

#### **Progressive Enhancement**

**Loading States:**
- Show skeleton screens during initial load
- Display progress indicators for long operations
- Provide estimated time remaining for document processing

**Error Recovery:**
- Offer retry buttons for failed operations
- Suggest alternative actions
- Maintain user input on errors

**Feedback Mechanisms:**
- Toast notifications for success/error
- Inline validation messages
- Confirmation dialogs for destructive actions

---

#### **Accessibility Improvements**

```html
<!-- Semantic HTML -->
<main role="main" aria-label="Chat interface">
    <section aria-label="Conversation history">
        <div role="log" aria-live="polite" aria-atomic="false">
            <!-- Messages appear here -->
        </div>
    </section>
    
    <form aria-label="Send message">
        <label for="chat-input" class="sr-only">Type your question</label>
        <input 
            id="chat-input" 
            type="text" 
            aria-describedby="input-help"
            placeholder="Ask a question..."
        />
        <button type="submit" aria-label="Send message">
            <span aria-hidden="true">→</span>
        </button>
    </form>
</main>
```

**Keyboard Navigation:**
- Tab order follows logical flow
- Escape key closes modals
- Enter key submits forms
- Arrow keys navigate lists

---

### **Monitoring and Observability**

#### **Metrics Collection**

```python
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
query_counter = Counter('rag_queries_total', 'Total number of queries')
query_duration = Histogram('rag_query_duration_seconds', 'Query processing time')
active_users = Gauge('rag_active_users', 'Number of active users')
document_count = Gauge('rag_documents_total', 'Total number of indexed documents')

# Use in code
@query_duration.time()
def main_rag_pipeline(query):
    query_counter.inc()
    # ... processing logic
```

#### **Health Checks**

```python
@app.route('/api/health')
def health_check():
    checks = {
        "ollama": check_ollama_health(),
        "vector_db": check_vector_db_health(),
        "disk_space": check_disk_space(),
        "memory": check_memory_usage()
    }
    
    status = "healthy" if all(checks.values()) else "unhealthy"
    
    return jsonify({
        "status": status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }), 200 if status == "healthy" else 503
```

---

## **C - COMPLETION**

### **Deployment Guide**

#### **Prerequisites**

**System Requirements:**
- Ubuntu 20.04+ or similar Linux distribution
- 16GB RAM minimum (32GB recommended)
- 100GB+ SSD storage
- 8+ CPU cores
- Optional: NVIDIA GPU with CUDA support

**Software Dependencies:**
- Python 3.10+
- Ollama
- Git
- pip

---

#### **Step 1: Server Setup**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install python3.10 python3.10-venv python3-pip -y

# Install Ollama
curl https://ollama.ai/install.sh | sh

# Verify Ollama installation
ollama --version

# Pull required models
ollama pull nomic-embed-text
ollama pull llama2  # or mistral, or your preferred model

# Verify models are available
ollama list
```

---

#### **Step 2: Application Deployment**

```bash
# Clone repository
git clone https://github.com/your-org/rag-ollama-app.git
cd rag-ollama-app

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create necessary directories
mkdir -p data/uploads data/processed data/vector_db logs

# Copy and configure environment variables
cp .env.example .env
nano .env  # Edit configuration

# Initialize database
python src/init_db.py

# Run database migrations (if applicable)
python src/migrate.py
```

---

#### **Step 3: Configuration**

```bash
# .env file
APP_NAME=RAG Ollama App
DEBUG=False
SECRET_KEY=your-secret-key-here

OLLAMA_BASE_URL=https://ollama.example.com  # Or http://localhost:11434 for local development
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_LLM_MODEL=llama2

VECTOR_DB_PATH=./data/vector_db
MAX_FILE_SIZE_MB=100
CHUNK_SIZE=500
CHUNK_OVERLAP=50

LOG_LEVEL=INFO
```

---

#### **Step 4: Running the Application**

**Development Mode:**
```bash
# Activate virtual environment
source venv/bin/activate

# Run Flask development server
python src/app.py

# Application will be available at ${API_BASE_URL} (configure in environment variables)
```

**Production Mode with Gunicorn:**
```bash
# Install Gunicorn
pip install gunicorn

# Run with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 src.app:app

# Or use the provided script
./scripts/start_production.sh
```

---

#### **Step 5: Nginx Configuration (Optional)**

```nginx
# /etc/nginx/sites-available/rag-app
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for streaming
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    location /static {
        alias /path/to/rag-ollama-app/static;
        expires 30d;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/rag-app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

#### **Step 6: Systemd Service (Production)**

```ini
# /etc/systemd/system/rag-app.service
[Unit]
Description=RAG Ollama Application
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/path/to/rag-ollama-app
Environment="PATH=/path/to/rag-ollama-app/venv/bin"
ExecStart=/path/to/rag-ollama-app/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 --timeout 120 src.app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable rag-app
sudo systemctl start rag-app
sudo systemctl status rag-app
```

---

### **Testing Procedures**

#### **Pre-Deployment Testing Checklist**

- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Performance benchmarks meet requirements
- [ ] Security scan completed (no critical vulnerabilities)
- [ ] Documentation is up-to-date
- [ ] Configuration files reviewed
- [ ] Backup procedures tested

```bash
# Post-Deployment Testing (continued)

# 1. Health Check
curl ${API_BASE_URL}/api/health  # Or https://api.example.com/api/health for production

# Expected response:
# {
#   "status": "healthy",
#   "checks": {
#     "ollama": true,
#     "vector_db": true,
#     "disk_space": true,
#     "memory": true
#   }
# }

# 2. Test Document Upload
curl -X POST ${API_BASE_URL}/api/upload \
  -F "documents=@test_document.pdf"

# 3. Test Query
curl -X POST ${API_BASE_URL}/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the main topic of the uploaded document?"}'

# 4. Load Testing (using Apache Bench)
ab -n 100 -c 10 -p query.json -T application/json \
  ${API_BASE_URL}/api/chat
```

#### **Smoke Tests**

```python
# tests/smoke_tests.py
import requests
import time

def run_smoke_tests(base_url=os.getenv("API_BASE_URL", "http://localhost:5000")):
    results = []
    
    # Test 1: Health endpoint
    try:
        response = requests.get(f"{base_url}/api/health", timeout=5)
        results.append(("Health Check", response.status_code == 200))
    except Exception as e:
        results.append(("Health Check", False))
    
    # Test 2: Upload document
    try:
        with open("tests/fixtures/sample.pdf", "rb") as f:
            files = {"documents": f}
            response = requests.post(f"{base_url}/api/upload", files=files, timeout=30)
        results.append(("Document Upload", response.status_code == 200))
    except Exception as e:
        results.append(("Document Upload", False))
    
    # Test 3: Query
    try:
        data = {"query": "Test query"}
        response = requests.post(f"{base_url}/api/chat", json=data, timeout=10)
        results.append(("Query Processing", response.status_code == 200))
    except Exception as e:
        results.append(("Query Processing", False))
    
    # Print results
    print("\n=== Smoke Test Results ===")
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    return all(result[1] for result in results)

if __name__ == "__main__":
    success = run_smoke_tests()
    exit(0 if success else 1)
```

---

### **Maintenance Procedures**

#### **Regular Maintenance Tasks**

**Daily:**
- Monitor application logs for errors
- Check disk space usage
- Verify Ollama service is running
- Review query performance metrics

**Weekly:**
- Analyze slow queries and optimize
- Review and rotate logs
- Check for security updates
- Backup vector database

**Monthly:**
- Update dependencies
- Review and optimize vector database indices
- Analyze user feedback and usage patterns
- Performance tuning based on metrics

---

#### **Backup Strategy**

```bash
#!/bin/bash
# scripts/backup.sh

BACKUP_DIR="/backups/rag-app"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/backup_$TIMESTAMP"

# Create backup directory
mkdir -p "$BACKUP_PATH"

# Backup vector database
echo "Backing up vector database..."
cp -r data/vector_db "$BACKUP_PATH/"

# Backup uploaded documents
echo "Backing up documents..."
cp -r data/uploads "$BACKUP_PATH/"
cp -r data/processed "$BACKUP_PATH/"

# Backup configuration
echo "Backing up configuration..."
cp .env "$BACKUP_PATH/"
cp config/*.py "$BACKUP_PATH/"

# Backup metadata database (if using SQLite)
if [ -f "data/metadata.db" ]; then
    cp data/metadata.db "$BACKUP_PATH/"
fi

# Create archive
echo "Creating archive..."
tar -czf "$BACKUP_PATH.tar.gz" -C "$BACKUP_DIR" "backup_$TIMESTAMP"

# Remove uncompressed backup
rm -rf "$BACKUP_PATH"

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/backup_*.tar.gz | tail -n +8 | xargs -r rm

echo "Backup completed: $BACKUP_PATH.tar.gz"
```

**Automated Backup with Cron:**
```bash
# Add to crontab
crontab -e

# Run backup daily at 2 AM
0 2 * * * /path/to/rag-ollama-app/scripts/backup.sh >> /var/log/rag-backup.log 2>&1
```

---

#### **Restore Procedure**

```bash
#!/bin/bash
# scripts/restore.sh

if [ -z "$1" ]; then
    echo "Usage: ./restore.sh <backup_file.tar.gz>"
    exit 1
fi

BACKUP_FILE=$1
RESTORE_DIR="/tmp/rag-restore"

# Stop application
echo "Stopping application..."
sudo systemctl stop rag-app

# Extract backup
echo "Extracting backup..."
mkdir -p "$RESTORE_DIR"
tar -xzf "$BACKUP_FILE" -C "$RESTORE_DIR"

# Restore files
echo "Restoring files..."
BACKUP_FOLDER=$(ls "$RESTORE_DIR")
cp -r "$RESTORE_DIR/$BACKUP_FOLDER/vector_db" data/
cp -r "$RESTORE_DIR/$BACKUP_FOLDER/uploads" data/
cp -r "$RESTORE_DIR/$BACKUP_FOLDER/processed" data/

# Restore configuration (with confirmation)
read -p "Restore configuration files? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cp "$RESTORE_DIR/$BACKUP_FOLDER/.env" .
fi

# Cleanup
rm -rf "$RESTORE_DIR"

# Start application
echo "Starting application..."
sudo systemctl start rag-app

echo "Restore completed!"
```

---

#### **Log Management**

```python
# config/logging_config.py
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import os

def setup_logging(app):
    """Configure application logging"""
    
    # Create logs directory
    os.makedirs('logs', exist_ok=True)
    
    # Application log (rotating by size)
    app_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # Error log (rotating by time)
    error_handler = TimedRotatingFileHandler(
        'logs/error.log',
        when='midnight',
        interval=1,
        backupCount=30
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s'
    ))
    
    # Performance log
    perf_handler = RotatingFileHandler(
        'logs/performance.log',
        maxBytes=10485760,
        backupCount=5
    )
    perf_handler.setLevel(logging.INFO)
    perf_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(message)s'
    ))
    
    # Add handlers to app logger
    app.logger.addHandler(app_handler)
    app.logger.addHandler(error_handler)
    
    # Create performance logger
    perf_logger = logging.getLogger('performance')
    perf_logger.addHandler(perf_handler)
    perf_logger.setLevel(logging.INFO)
    
    return app.logger, perf_logger
```

---

### **Monitoring and Alerting**

#### **Monitoring Dashboard Setup**

```python
# src/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from flask import Response
import psutil
import time

# Define metrics
request_count = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')
query_count = Counter('rag_queries_total', 'Total RAG queries')
query_duration = Histogram('rag_query_duration_seconds', 'RAG query duration')
document_count = Gauge('rag_documents_total', 'Total indexed documents')
embedding_generation_duration = Histogram('embedding_generation_seconds', 'Embedding generation time')
vector_search_duration = Histogram('vector_search_seconds', 'Vector search time')
llm_generation_duration = Histogram('llm_generation_seconds', 'LLM generation time')

# System metrics
cpu_usage = Gauge('system_cpu_usage_percent', 'CPU usage percentage')
memory_usage = Gauge('system_memory_usage_percent', 'Memory usage percentage')
disk_usage = Gauge('system_disk_usage_percent', 'Disk usage percentage')

def update_system_metrics():
    """Update system resource metrics"""
    cpu_usage.set(psutil.cpu_percent())
    memory_usage.set(psutil.virtual_memory().percent)
    disk_usage.set(psutil.disk_usage('/').percent)

@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    update_system_metrics()
    return Response(generate_latest(), mimetype='text/plain')
```

#### **Alert Configuration (Prometheus AlertManager)**

```yaml
# alertmanager/alerts.yml
groups:
  - name: rag_app_alerts
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors/sec"
      
      # Slow queries
      - alert: SlowQueries
        expr: histogram_quantile(0.95, rate(rag_query_duration_seconds_bucket[5m])) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Queries are slow"
          description: "95th percentile query time is {{ $value }}s"
      
      # High memory usage
      - alert: HighMemoryUsage
        expr: system_memory_usage_percent > 90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value }}%"
      
      # Disk space low
      - alert: LowDiskSpace
        expr: system_disk_usage_percent > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low disk space"
          description: "Disk usage is {{ $value }}%"
      
      # Ollama service down
      - alert: OllamaServiceDown
        expr: up{job="ollama"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Ollama service is down"
          description: "Ollama service has been down for 2 minutes"
```

---

### **Troubleshooting Guide**

#### **Common Issues and Solutions**

**Issue 1: Ollama Connection Errors**

*Symptoms:*
- "Connection refused" errors in logs
- Embedding generation fails
- LLM responses timeout

*Solutions:*
```bash
# Check if Ollama is running
systemctl status ollama

# Restart Ollama service
sudo systemctl restart ollama

# Check Ollama logs
journalctl -u ollama -f

# Verify models are loaded
ollama list

# Test Ollama directly
curl ${OLLAMA_BASE_URL}/api/generate -d '{
  "model": "llama2",
  "prompt": "Hello"
}'
```

---

**Issue 2: Slow Query Performance**

*Symptoms:*
- Queries take longer than 5 seconds
- Timeout errors
- High CPU usage

*Solutions:*
```python
# Check vector database size
from src.vector_store.vector_db import VectorDB
db = VectorDB()
print(f"Total documents: {db.count()}")

# Rebuild index for better performance
db.rebuild_index()

# Check if too many results being retrieved
# Reduce top_k in config
settings.TOP_K_RESULTS = 3  # Instead of 5

# Enable query caching
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_vector_search(query_hash, top_k):
    return vector_search(query_hash, top_k)
```

---

**Issue 3: Out of Memory Errors**

*Symptoms:*
- Application crashes
- "MemoryError" in logs
- System becomes unresponsive

*Solutions:*
```bash
# Check memory usage
free -h
htop

# Reduce batch size for embedding generation
# In config/settings.py
BATCH_SIZE = 16  # Instead of 32

# Limit concurrent requests
MAX_CONCURRENT_REQUESTS = 5  # Instead of 10

# Clear vector database cache
python scripts/clear_cache.py

# Restart application to free memory
sudo systemctl restart rag-app
```

---

**Issue 4: Document Processing Failures**

*Symptoms:*
- Upload succeeds but indexing fails
- "DocumentProcessingError" in logs
- Documents stuck in "processing" status

*Solutions:*
```python
# Check document format
from src.document_processor.pdf_processor import PDFProcessor

processor = PDFProcessor()
try:
    text = processor.extract_text("problematic_file.pdf")
    print(f"Extracted {len(text)} characters")
except Exception as e:
    print(f"Error: {e}")

# Try alternative PDF library
# Switch from PyPDF2 to pdfplumber in config

# For corrupted files, use repair tool
pdftk broken.pdf output fixed.pdf

# Reprocess failed documents
python scripts/reprocess_failed.py
```

---

**Issue 5: Inaccurate Answers**

*Symptoms:*
- Answers don't match source documents
- Hallucinations in responses
- Wrong citations

*Solutions:*
```python
# Increase similarity threshold
settings.SIMILARITY_THRESHOLD = 0.8  # Instead of 0.7

# Improve prompt template
PROMPT_TEMPLATE = """You are a helpful assistant. Answer ONLY based on the context below.
If you cannot answer from the context, say "I don't have enough information."

Context:
{context}

Question: {question}

Answer (with citations):"""

# Enable re-ranking
from sentence_transformers import CrossEncoder
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def rerank_results(query, results):
    pairs = [[query, r.text] for r in results]
    scores = reranker.predict(pairs)
    return sorted(zip(results, scores), key=lambda x: x[1], reverse=True)

# Adjust chunk size for better context
settings.CHUNK_SIZE = 750  # Larger chunks
settings.CHUNK_OVERLAP = 100  # More overlap
```

---

### **User Documentation**

#### **Quick Start Guide**

**For End Users:**

1. **Accessing the Application**
   - Open web browser
   - Navigate to `http://your-server-address`
   - Log in with provided credentials

2. **Uploading Documents**
   - Click "Upload Documents" button
   - Select PDF or Excel files (max 100MB each)
   - Wait for processing to complete
   - Documents appear in "My Documents" list

3. **Asking Questions**
   - Type question in chat box
   - Press Enter or click Send
   - View answer with source citations
   - Click citations to see source passages

4. **Managing Documents**
   - Go to "Document Management"
   - Search or filter documents
   - Click trash icon to delete
   - Confirm deletion

---

#### **Administrator Guide**

**User Management:**
```python
# Create new user
python scripts/create_user.py --username john --role user

# List all users
python scripts/list_users.py

# Delete user
python scripts/delete_user.py --username john

# Change user role
python scripts/update_user.py --username john --role admin
```

**System Configuration:**
```bash
# Update Ollama model
ollama pull llama2:latest
# Update config to use new model
nano .env
# Set: OLLAMA_LLM_MODEL=llama2:latest
# Restart application
sudo systemctl restart rag-app

# Adjust performance settings
nano config/settings.py
# Modify: CHUNK_SIZE, TOP_K_RESULTS, BATCH_SIZE
# Restart application
```

**Monitoring:**
```bash
# View real-time logs
tail -f logs/app.log

# Check application status
sudo systemctl status rag-app

# View metrics
curl ${API_BASE_URL}/metrics

# Check resource usage
htop
df -h
```

---

### **API Documentation**

#### **Endpoints**

**POST /api/chat**

Request:
```json
{
  "query": "What are the main findings?",
  "conversation_id": "optional-uuid"
}
```

Response:
```json
{
  "conversation_id": "uuid",
  "answer": "The main findings are... [1][2]",
  "sources": [
    {
      "number": 1,
      "filename": "report.pdf",
      "text": "Relevant passage...",
      "score": 0.92,
      "document_id": "doc-uuid"
    }
  ],
  "metadata": {
    "query_time": 2.3,
    "num_sources": 2,
    "model": "llama2"
  }
}
```

---

**POST /api/upload**

Request (multipart/form-data):
```
documents: [file1.pdf, file2.xlsx]
```

Response:
```json
{
  "uploaded": 2,
  "failed": 0,
  "details": [
    {
      "filename": "file1.pdf",
      "document_id": "doc-uuid-1",
      "status": "success"
    },
    {
      "filename": "file2.xlsx",
      "document_id": "doc-uuid-2",
      "status": "success"
    }
  ]
}
```

---

**GET /api/documents**

Query Parameters:
- `page`: Page number (default: 1)
- `per_page`: Results per page (default: 50)
- `search`: Search term (optional)

Response:
```json
{
  "documents": [
    {
      "document_id": "uuid",
      "filename": "report.pdf",
      "file_type": "pdf",
      "file_size": 1048576,
      "upload_date": "2025-11-24T02:35:00Z",
      "chunk_count": 45,
      "status": "indexed"
    }
  ],
  "total": 150,
  "page": 1,
  "per_page": 50
}
```

---

**DELETE /api/documents/{document_id}**

Response:
```json
{
  "message": "Document deleted successfully",
  "document_id": "uuid"
}
```

---

### **Future Enhancements**

#### **Phase 2 Features**

1. **Multi-language Support**
   - Detect document language automatically
   - Use language-specific embedding models
   - Translate queries if needed

2. **Advanced Document Types**
   - Word documents (.docx)
   - PowerPoint presentations (.pptx)
   - HTML/Markdown files
   - OCR for scanned PDFs

3. **Conversation Memory**
   - Maintain conversation context
   - Reference previous questions
   - Follow-up question handling

4. **Document Versioning**
   - Track document updates
   - Compare versions
   - Rollback capability

5. **Advanced Search**
   - Filters by date, type, author
   - Boolean search operators
   - Saved searches

---

#### **Phase 3 Features**

1. **Collaborative Features**
   - Share conversations
   - Annotate documents
   - Team workspaces

2. **Analytics Dashboard**
   - Usage statistics
   - Popular queries
   - Document access patterns
   - User engagement metrics

3. **API Integrations**
   - Slack bot
   - Microsoft Teams integration
   - REST API for external apps

4. **Advanced RAG Techniques**
   - Hybrid search (keyword + semantic)
   - Query expansion
   - Multi-hop reasoning
   - Self-reflection and verification

---

### **Conclusion**

This SPARC documentation provides a comprehensive blueprint for building a production-ready RAG application using Ollama. The system is designed to handle large document collections (7,500+) while maintaining privacy through secure server-side processing with flexible deployment options including cloud platforms (AWS, Azure, GCP), Docker containers, and Kubernetes orchestration.

**Key Strengths:**
- **Privacy-First**: All processing occurs on the server with configurable security controls
- **Scalable**: Handles large document collections efficiently
- **Transparent**: Clear source attribution for all answers
- **Maintainable**: Modular architecture with comprehensive documentation
- **Production-Ready**: Includes deployment, monitoring, and maintenance procedures

**Success Metrics:**
- Query response time < 5 seconds (95th percentile)
- Document indexing rate > 10 docs/minute
- System uptime > 99%
- User satisfaction > 4/5 stars

The application is ready for deployment and can be extended with additional features as requirements evolve.
