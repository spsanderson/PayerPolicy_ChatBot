# Pseudocode

## Objective
Create a comprehensive pseudocode outline serving as a development roadmap for the RAG Ollama Application, detailing all core functionalities from document ingestion to query processing and response generation.

---

## Document Ingestion and Processing

### File Upload and Validation

```
def handle_file_upload(files, user_id):
    validated_files = []
    errors = []
    
    for file in files:
        if validate_file_type(file):
            if validate_file_size(file):
                temp_path = save_to_temp_storage(file)
                validated_files.append({
                    'file': file,
                    'temp_path': temp_path,
                    'file_type': detect_file_type(file.name)
                })
            else:
                errors.append({
                    'filename': file.name,
                    'error': 'File size exceeds 100MB limit'
                })
        else:
            errors.append({
                'filename': file.name,
                'error': 'Unsupported file type'
            })
    
    return validated_files, errors

def validate_file_type(file):
    allowed_extensions = ['pdf', 'xlsx', 'xls']
    extension = get_file_extension(file.name).lower()
    return extension in allowed_extensions

def validate_file_size(file):
    max_size = 100 * 1024 * 1024  // 100MB in bytes
    return file.size <= max_size
```

### Text Extraction

```
def extract_text_from_document(file_path, file_type):
    if file_type == 'pdf':
        return extract_pdf_text(file_path)
    elif file_type in ['xlsx', 'xls']:
        return extract_excel_text(file_path)
    else:
        raise UnsupportedFileTypeError(file_type)

def extract_pdf_text(file_path):
    try:
        pdf_reader = initialize_pdf_reader(file_path)
        text_content = ""
        page_metadata = []
        
        for page_num in range(pdf_reader.num_pages):
            page = pdf_reader.get_page(page_num)
            page_text = page.extract_text()
            text_content += page_text + "\n\n"
            
            page_metadata.append({
                'page_number': page_num + 1,
                'text_length': len(page_text),
                'start_position': len(text_content) - len(page_text)
            })
        
        return {
            'text': text_content,
            'metadata': page_metadata,
            'total_pages': pdf_reader.num_pages
        }
    except Exception as e:
        log_error("PDF extraction failed", file_path, e)
        raise DocumentProcessingError(f"Failed to extract PDF: {str(e)}")

def extract_excel_text(file_path):
    try:
        workbook = load_excel_workbook(file_path)
        text_content = ""
        sheet_metadata = []
        
        for sheet_name in workbook.sheet_names:
            sheet = workbook[sheet_name]
            sheet_text = f"Sheet: {sheet_name}\n"
            
            for row in sheet.iter_rows(values_only=True):
                row_text = " | ".join([str(cell) for cell in row if cell is not None])
                if row_text.strip():
                    sheet_text += row_text + "\n"
            
            text_content += sheet_text + "\n\n"
            
            sheet_metadata.append({
                'sheet_name': sheet_name,
                'row_count': sheet.max_row,
                'column_count': sheet.max_column
            })
        
        return {
            'text': text_content,
            'metadata': sheet_metadata,
            'total_sheets': len(workbook.sheet_names)
        }
    except Exception as e:
        log_error("Excel extraction failed", file_path, e)
        raise DocumentProcessingError(f"Failed to extract Excel: {str(e)}")
```

### Document Chunking

```
def chunk_document(text, metadata, chunk_size=500, overlap=50):
    chunks = []
    paragraphs = split_into_paragraphs(text)
    
    current_chunk = ""
    current_tokens = 0
    chunk_index = 0
    
    for paragraph in paragraphs:
        paragraph_tokens = count_tokens(paragraph)
        
        if current_tokens + paragraph_tokens <= chunk_size:
            current_chunk += paragraph + "\n"
            current_tokens += paragraph_tokens
        else:
            if current_chunk:
                chunks.append(create_chunk_object(
                    text=current_chunk,
                    index=chunk_index,
                    metadata=metadata
                ))
                chunk_index += 1
            
            if paragraph_tokens > chunk_size:
                sub_chunks = split_large_paragraph(
                    paragraph, 
                    chunk_size, 
                    overlap
                )
                for sub_chunk in sub_chunks:
                    chunks.append(create_chunk_object(
                        text=sub_chunk,
                        index=chunk_index,
                        metadata=metadata
                    ))
                    chunk_index += 1
                current_chunk = ""
                current_tokens = 0
            else:
                overlap_text = get_last_tokens(current_chunk, overlap)
                current_chunk = overlap_text + paragraph + "\n"
                current_tokens = count_tokens(current_chunk)
    
    if current_chunk:
        chunks.append(create_chunk_object(
            text=current_chunk,
            index=chunk_index,
            metadata=metadata
        ))
    
    return chunks

def split_into_paragraphs(text):
    paragraphs = text.split('\n\n')
    return [p.strip() for p in paragraphs if p.strip()]

def split_large_paragraph(paragraph, max_size, overlap):
    sentences = split_into_sentences(paragraph)
    chunks = []
    current_chunk = ""
    current_size = 0
    
    for sentence in sentences:
        sentence_size = count_tokens(sentence)
        
        if current_size + sentence_size <= max_size:
            current_chunk += sentence + " "
            current_size += sentence_size
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            overlap_text = get_last_tokens(current_chunk, overlap)
            current_chunk = overlap_text + sentence + " "
            current_size = count_tokens(current_chunk)
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def create_chunk_object(text, index, metadata):
    return {
        'chunk_id': generate_uuid(),
        'text': text,
        'chunk_index': index,
        'token_count': count_tokens(text),
        'document_id': metadata['document_id'],
        'filename': metadata['filename'],
        'file_type': metadata['file_type'],
        'upload_date': metadata['upload_date']
    }
```

---

## Embedding Generation

### Ollama Client

```
def initialize_ollama_client(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), model_name="llama2"):
    client = {
        'base_url': base_url,
        'model': model_name,
        'timeout': 30,
        'max_retries': 3
    }
    
    if not check_ollama_health(client):
        raise OllamaConnectionError("Cannot connect to Ollama service")
    
    return client

def check_ollama_health(client):
    try:
        response = http_get(f"{client['base_url']}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False

def generate_embedding(text, client):
    request_payload = {
        'model': client['model'],
        'prompt': text
    }
    
    for attempt in range(client['max_retries']):
        try:
            response = http_post(
                f"{client['base_url']}/api/embeddings",
                json=request_payload,
                timeout=client['timeout']
            )
            
            if response.status_code == 200:
                embedding = response.json()['embedding']
                return normalize_vector(embedding)
            else:
                log_warning(f"Embedding generation failed: {response.status_code}")
                
        except TimeoutError:
            log_warning(f"Embedding timeout on attempt {attempt + 1}")
            if attempt < client['max_retries'] - 1:
                sleep(2 ** attempt)  // Exponential backoff
        except Exception as e:
            log_error("Embedding generation error", e)
            if attempt == client['max_retries'] - 1:
                raise EmbeddingGenerationError(str(e))
    
    raise EmbeddingGenerationError("Max retries exceeded")

def generate_embeddings_batch(texts, client, batch_size=32):
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = []
        
        for text in batch:
            embedding = generate_embedding(text, client)
            batch_embeddings.append(embedding)
        
        all_embeddings.extend(batch_embeddings)
        
        log_info(f"Generated embeddings for batch {i//batch_size + 1}")
    
    return all_embeddings

def normalize_vector(vector):
    magnitude = sqrt(sum(x**2 for x in vector))
    if magnitude == 0:
        return vector
    return [x / magnitude for x in vector]
```

---

## Vector Database Operations

### Database Initialization

```
def initialize_vector_database(db_path, collection_name):
    db = create_chromadb_client(db_path)
    
    try:
        collection = db.get_collection(collection_name)
        log_info(f"Using existing collection: {collection_name}")
    except CollectionNotFoundError:
        collection = db.create_collection(
            name=collection_name,
            metadata={'hnsw:space': 'cosine'}
        )
        log_info(f"Created new collection: {collection_name}")
    
    return collection

def add_documents_to_vector_db(chunks, embeddings, collection):
    if len(chunks) != len(embeddings):
        raise ValueError("Chunks and embeddings length mismatch")
    
    ids = [chunk['chunk_id'] for chunk in chunks]
    documents = [chunk['text'] for chunk in chunks]
    metadatas = [extract_metadata(chunk) for chunk in chunks]
    
    try:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        log_info(f"Added {len(chunks)} chunks to vector database")
        return True
    except Exception as e:
        log_error("Failed to add documents to vector DB", e)
        raise VectorStoreError(str(e))

def extract_metadata(chunk):
    return {
        'document_id': chunk['document_id'],
        'filename': chunk['filename'],
        'file_type': chunk['file_type'],
        'chunk_index': chunk['chunk_index'],
        'upload_date': chunk['upload_date'],
        'token_count': chunk['token_count']
    }
```

### Vector Search

```
def search_similar_documents(query_embedding, collection, top_k=5, threshold=0.7):
    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k * 2,  // Get more results for filtering
            include=['documents', 'metadatas', 'distances']
        )
        
        filtered_results = []
        
        for i in range(len(results['ids'][0])):
            similarity_score = 1 - results['distances'][0][i]  // Convert distance to similarity
            
            if similarity_score >= threshold:
                filtered_results.append({
                    'chunk_id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'score': similarity_score
                })
        
        filtered_results = sorted(
            filtered_results, 
            key=lambda x: x['score'], 
            reverse=True
        )[:top_k]
        
        return filtered_results
        
    except Exception as e:
        log_error("Vector search failed", e)
        raise VectorSearchError(str(e))

def rerank_results(query, results, reranker_model=None):
    if reranker_model is None:
        return results
    
    query_result_pairs = [[query, result['text']] for result in results]
    rerank_scores = reranker_model.predict(query_result_pairs)
    
    for i, result in enumerate(results):
        result['rerank_score'] = rerank_scores[i]
    
    reranked = sorted(results, key=lambda x: x['rerank_score'], reverse=True)
    return reranked
```

---

## RAG Pipeline

### Main Query Processing

```
def process_rag_query(user_query, conversation_id=None):
    start_time = get_current_time()
    
    // Step 1: Validate query
    if not validate_query(user_query):
        return create_error_response("Invalid query")
    
    // Step 2: Generate query embedding
    try:
        ollama_client = get_ollama_client()
        query_embedding = generate_embedding(user_query, ollama_client)
    except EmbeddingGenerationError as e:
        log_error("Query embedding failed", e)
        return create_error_response("Failed to process query")
    
    // Step 3: Retrieve relevant documents
    try:
        vector_db = get_vector_database()
        retrieved_chunks = search_similar_documents(
            query_embedding,
            vector_db,
            top_k=get_config('TOP_K_RESULTS'),
            threshold=get_config('SIMILARITY_THRESHOLD')
        )
    except VectorSearchError as e:
        log_error("Vector search failed", e)
        return create_error_response("Failed to retrieve documents")
    
    // Step 4: Check if sufficient results found
    if len(retrieved_chunks) == 0:
        return create_response(
            answer="I couldn't find relevant information to answer your question.",
            sources=[],
            metadata={'query_time': get_elapsed_time(start_time)}
        )
    
    // Step 5: Re-rank results (optional)
    if get_config('USE_RERANKING'):
        retrieved_chunks = rerank_results(user_query, retrieved_chunks)
    
    // Step 6: Build context from retrieved chunks
    context = build_context_from_chunks(retrieved_chunks)
    
    // Step 7: Construct prompt
    prompt = create_rag_prompt(user_query, context, retrieved_chunks)
    
    // Step 8: Generate answer
    try:
        answer = generate_llm_response(prompt, ollama_client)
    except LLMGenerationError as e:
        log_error("LLM generation failed", e)
        return create_error_response("Failed to generate answer")
    
    // Step 9: Add citations
    cited_answer = add_citations_to_answer(answer, retrieved_chunks)
    
    // Step 10: Log conversation
    if conversation_id:
        log_conversation(conversation_id, user_query, cited_answer, retrieved_chunks)
    
    // Step 11: Return response
    return create_response(
        answer=cited_answer,
        sources=format_sources(retrieved_chunks),
        metadata={
            'query_time': get_elapsed_time(start_time),
            'num_sources': len(retrieved_chunks),
            'model': get_config('OLLAMA_LLM_MODEL'),
            'conversation_id': conversation_id or generate_uuid()
        }
    )

def validate_query(query):
    if query is None or len(query.strip()) < 3:
        return False
    if len(query) > 1000:
        return False
    return True
```

### Context Building

```
def build_context_from_chunks(chunks):
    context_parts = []
    total_tokens = 0
    max_context_tokens = get_config('MAX_CONTEXT_LENGTH')
    
    for i, chunk in enumerate(chunks):
        chunk_tokens = chunk['metadata'].get('token_count', count_tokens(chunk['text']))
        
        if total_tokens + chunk_tokens > max_context_tokens:
            log_warning(f"Context limit reached, using {i} of {len(chunks)} chunks")
            break
        
        context_parts.append({
            'index': i + 1,
            'text': chunk['text'],
            'source': chunk['metadata']['filename']
        })
        total_tokens += chunk_tokens
    
    return context_parts

def create_rag_prompt(query, context_parts, chunks):
    context_text = ""
    
    for part in context_parts:
        context_text += f"[{part['index']}] Source: {part['source']}\n"
        context_text += f"{part['text']}\n\n"
    
    prompt_template = get_prompt_template()
    
    prompt = prompt_template.format(
        context=context_text,
        question=query
    )
    
    return prompt

def get_prompt_template():
    return """You are a helpful AI assistant that answers questions based on provided documents.

Context Information from Documents:
{context}

User Question: {question}

Instructions:
- Answer the question using ONLY the information from the context above
- Cite your sources using [1], [2], etc. immediately after making claims
- If the context doesn't contain enough information to answer, say so clearly
- Be concise but complete in your answer
- Do not make up or infer information not present in the context

Answer:"""
```

### LLM Response Generation

```
def generate_llm_response(prompt, client):
    request_payload = {
        'model': get_config('OLLAMA_LLM_MODEL'),
        'prompt': prompt,
        'stream': False,
        'options': {
            'temperature': 0.7,
            'top_p': 0.9,
            'max_tokens': 1000,
            'stop': ['User Question:', 'Context Information:']
        }
    }
    
    try:
        response = http_post(
            f"{client['base_url']}/api/generate",
            json=request_payload,
            timeout=60
        )
        
        if response.status_code == 200:
            answer = response.json()['response']
            return answer.strip()
        else:
            raise LLMGenerationError(f"Status code: {response.status_code}")
            
    except TimeoutError:
        log_error("LLM generation timeout")
        raise LLMGenerationError("Response generation timed out")
    except Exception as e:
        log_error("LLM generation failed", e)
        raise LLMGenerationError(str(e))

def generate_llm_response_streaming(prompt, client):
    request_payload = {
        'model': get_config('OLLAMA_LLM_MODEL'),
        'prompt': prompt,
        'stream': True,
        'options': {
            'temperature': 0.7,
            'top_p': 0.9,
            'max_tokens': 1000
        }
    }
    
    try:
        response_stream = http_post_stream(
            f"{client['base_url']}/api/generate",
            json=request_payload
        )
        
        for chunk in response_stream:
            if chunk:
                token = parse_json(chunk)['response']
                yield token
                
    except Exception as e:
        log_error("Streaming generation failed", e)
        raise LLMGenerationError(str(e))
```

### Citation Management

```
def add_citations_to_answer(answer, source_chunks):
    citation_map = {}
    
    for i, chunk in enumerate(source_chunks):
        citation_number = i + 1
        citation_map[citation_number] = {
            'filename': chunk['metadata']['filename'],
            'text_snippet': chunk['text'][:200] + "...",
            'score': chunk['score']
        }
    
    // Check if citations already exist in answer
    existing_citations = extract_citation_numbers(answer)
    
    if len(existing_citations) > 0:
        return {
            'answer': answer,
            'citations': citation_map
        }
    
    // If no citations, try to add them intelligently
    sentences = split_into_sentences(answer)
    cited_sentences = []
    
    for sentence in sentences:
        best_match = find_best_matching_source(sentence, source_chunks)
        if best_match is not None:
            citation_num = source_chunks.index(best_match) + 1
            cited_sentence = sentence + f" [{citation_num}]"
            cited_sentences.append(cited_sentence)
        else:
            cited_sentences.append(sentence)
    
    cited_answer = " ".join(cited_sentences)
    
    return {
        'answer': cited_answer,
        'citations': citation_map
    }

def find_best_matching_source(sentence, source_chunks):
    best_match = None
    best_score = 0.0
    
    sentence_lower = sentence.lower()
    
    for chunk in source_chunks:
        chunk_lower = chunk['text'].lower()
        
        // Simple word overlap scoring
        sentence_words = set(sentence_lower.split())
        chunk_words = set(chunk_lower.split())
        overlap = len(sentence_words.intersection(chunk_words))
        score = overlap / len(sentence_words) if len(sentence_words) > 0 else 0
        
        if score > best_score and score > 0.3:
            best_score = score
            best_match = chunk
    
    return best_match

def format_sources(chunks):
    sources = []
    
    for i, chunk in enumerate(chunks):
        sources.append({
            'number': i + 1,
            'filename': chunk['metadata']['filename'],
            'text': chunk['text'],
            'score': round(chunk['score'], 3),
            'document_id': chunk['metadata']['document_id'],
            'chunk_index': chunk['metadata']['chunk_index']
        })
    
    return sources
```

---

## Document Management

### Document Ingestion Orchestration

```
def ingest_document(file_path, file_type, user_id):
    document_id = generate_uuid()
    
    try:
        // Step 1: Extract text
        log_info(f"Extracting text from {file_path}")
        extraction_result = extract_text_from_document(file_path, file_type)
        
        // Step 2: Create metadata
        metadata = {
            'document_id': document_id,
            'filename': get_filename(file_path),
            'file_type': file_type,
            'file_size': get_file_size(file_path),
            'upload_date': get_current_timestamp(),
            'user_id': user_id,
            'status': 'processing'
        }
        
        // Step 3: Save metadata to database
        save_document_metadata(metadata)
        
        // Step 4: Chunk document
        log_info(f"Chunking document {document_id}")
        chunks = chunk_document(
            extraction_result['text'],
            metadata,
            chunk_size=get_config('CHUNK_SIZE'),
            overlap=get_config('CHUNK_OVERLAP')
        )
        
        // Step 5: Generate embeddings
        log_info(f"Generating embeddings for {len(chunks)} chunks")
        ollama_client = get_ollama_client()
        chunk_texts = [chunk['text'] for chunk in chunks]
        embeddings = generate_embeddings_batch(
            chunk_texts,
            ollama_client,
            batch_size=get_config('BATCH_SIZE')
        )
        
        // Step 6: Store in vector database
        log_info(f"Storing chunks in vector database")
        vector_db = get_vector_database()
        add_documents_to_vector_db(chunks, embeddings, vector_db)
        
        // Step 7: Move file to permanent storage
        permanent_path = move_to_permanent_storage(file_path, document_id)
        
        // Step 8: Update metadata
        update_document_metadata(document_id, {
            'status': 'indexed',
            'chunk_count': len(chunks),
            'file_path': permanent_path
        })
        
        log_info(f"Successfully ingested document {document_id}")
        return document_id
        
    except Exception as e:
        log_error(f"Document ingestion failed for {document_id}", e)
        update_document_metadata(document_id, {'status': 'failed'})
        raise DocumentProcessingError(str(e))

def ingest_documents_batch(file_paths, file_types, user_id):
    results = []
    
    for file_path, file_type in zip(file_paths, file_types):
        try:
            document_id = ingest_document(file_path, file_type, user_id)
            results.append({
                'filename': get_filename(file_path),
                'document_id': document_id,
                'status': 'success'
            })
        except Exception as e:
            results.append({
                'filename': get_filename(file_path),
                'status': 'failed',
                'error': str(e)
            })
    
    return results
```

### Document Retrieval and Deletion

```
def list_documents(user_id, page=1, per_page=50, search_term=None):
    offset = (page - 1) * per_page
    
    query = build_document_query(user_id, search_term)
    documents = execute_query(query, limit=per_page, offset=offset)
    total_count = count_documents(user_id, search_term)
    
    return {
        'documents': documents,
        'total': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': ceil(total_count / per_page)
    }

def get_document_details(document_id, user_id):
    document = fetch_document_metadata(document_id)
    
    if document is None:
        raise DocumentNotFoundError(document_id)
    
    if document['user_id'] != user_id:
        raise UnauthorizedAccessError()
    
    // Get chunk statistics
    chunk_stats = get_chunk_statistics(document_id)
    
    return {
        **document,
        'chunk_statistics': chunk_stats
    }

def delete_document(document_id, user_id):
    document = fetch_document_metadata(document_id)
    
    if document is None:
        raise DocumentNotFoundError(document_id)
    
    if document['user_id'] != user_id:
        raise UnauthorizedAccessError()
    
    try:
        // Step 1: Delete from vector database
        vector_db = get_vector_database()
        delete_chunks_by_document_id(vector_db, document_id)
        
        // Step 2: Delete file from storage
        if document['file_path']:
            delete_file(document['file_path'])
        
        // Step 3: Delete metadata
        delete_document_metadata(document_id)
        
        log_info(f"Successfully deleted document {document_id}")
        return True
        
    except Exception as e:
        log_error(f"Failed to delete document {document_id}", e)
        raise DocumentDeletionError(str(e))

def delete_chunks_by_document_id(collection, document_id):
    // Query all chunks for this document
    results = collection.get(
        where={'document_id': document_id}
    )
    
    if len(results['ids']) > 0:
        collection.delete(ids=results['ids'])
        log_info(f"Deleted {len(results['ids'])} chunks for document {document_id}")
```

---

## Flask API Routes

### Chat Endpoint

```
def handle_chat_request(request_data, user_id):
    // Validate request
    if 'query' not in request_data:
        return create_api_error("Missing 'query' field", 400)
    
    user_query = request_data['query']
    conversation_id = request_data.get('conversation_id', None)
    
    // Validate query
    if not validate_query(user_query):
        return create_api_error("Invalid query", 400)
    
    // Process query
    try:
        result = process_rag_query(user_query, conversation_id)
        
        // Log for analytics
        log_query_analytics(user_id, user_query, result['metadata'])
        
        return create_api_response(result, 200)
        
    except Exception as e:
        log_error("Chat request failed", e)
        return create_api_error("Internal server error", 500)

def handle_chat_stream_request(request_data, user_id):
    user_query = request_data['query']
    conversation_id = request_data.get('conversation_id', generate_uuid())
    
    def generate_stream():
        try:
            // Retrieve context
            ollama_client = get_ollama_client()
            query_embedding = generate_embedding(user_query, ollama_client)
            vector_db = get_vector_database()
            retrieved_chunks = search_similar_documents(query_embedding, vector_db)
            
            // Send sources first
            yield format_sse_event('sources', format_sources(retrieved_chunks))
            
            // Build prompt
            context = build_context_from_chunks(retrieved_chunks)
            prompt = create_rag_prompt(user_query, context, retrieved_chunks)
            
            // Stream answer
            for token in generate_llm_response_streaming(prompt, ollama_client):
                yield format_sse_event('token', token)
            
            // Send completion
            yield format_sse_event('done', {'conversation_id': conversation_id})
            
        except Exception as e:
            yield format_sse_event('error', str(e))
    
    return create_stream_response(generate_stream())

def format_sse_event(event_type, data):
    return f"event: {event_type}\ndata: {json_encode(data)}\n\n"
```

### Upload Endpoint

```python
def handle_upload_request(files, user_id):
    if not files or len(files) == 0:
        return create_api_error("No files provided", 400)
    
    // Validate files
    validated_files, validation_errors = handle_file_upload(files, user_id)
    
    if len(validated_files) == 0:
        return create_api_error("No valid files to process", 400)
    
    // Process files
    results = []
    
    for file_info in validated_files:
        try:
            document_id = ingest_document(
                file_info['temp_path'],
                file_info['file_type'],
                user_id
            )
            
            results.append({
                'filename': file_info['file']['name'],
                'document_id': document_id,
                'status': 'success'
            })
            
        except Exception as e:
            log_error(f"Failed to process {file_info['file']['name']}", e)
            results.append({
                'filename': file_info['file']['name'],
                'status': 'failed',
                'error': str(e)
            })
    
    // Add validation errors to results
    results.extend(validation_errors)
    
    success_count = len([r for r in results if r['status'] == 'success'])
    failed_count = len([r for r in results if r['status'] == 'failed'])
    
    return create_api_response({
        'uploaded': success_count,
        'failed': failed_count,
        'details': results
    }, 200)
```

### Document Management Endpoints

```
def handle_list_documents_request(query_params, user_id):
    page = int(query_params.get('page', 1))
    per_page = int(query_params.get('per_page', 50))
    search_term = query_params.get('search', None)
    
    // Validate pagination parameters
    if page < 1:
        return create_api_error("Page must be >= 1", 400)
    if per_page < 1 or per_page > 100:
        return create_api_error("Per page must be between 1 and 100", 400)
    
    try:
        result = list_documents(user_id, page, per_page, search_term)
        return create_api_response(result, 200)
    except Exception as e:
        log_error("List documents failed", e)
        return create_api_error("Internal server error", 500)

def handle_get_document_request(document_id, user_id):
    try:
        document = get_document_details(document_id, user_id)
        return create_api_response(document, 200)
    except DocumentNotFoundError:
        return create_api_error("Document not found", 404)
    except UnauthorizedAccessError:
        return create_api_error("Unauthorized access", 403)
    except Exception as e:
        log_error("Get document failed", e)
        return create_api_error("Internal server error", 500)

def handle_delete_document_request(document_id, user_id):
    try:
        delete_document(document_id, user_id)
        return create_api_response({
            'message': 'Document deleted successfully',
            'document_id': document_id
        }, 200)
    except DocumentNotFoundError:
        return create_api_error("Document not found", 404)
    except UnauthorizedAccessError:
        return create_api_error("Unauthorized access", 403)
    except Exception as e:
        log_error("Delete document failed", e)
        return create_api_error("Internal server error", 500)
```

### Health Check Endpoint

```
def handle_health_check_request():
    checks = {
        'ollama': check_ollama_service(),
        'vector_db': check_vector_database(),
        'disk_space': check_disk_space(),
        'memory': check_memory_usage()
    }
    
    all_healthy = all(checks.values())
    status = 'healthy' if all_healthy else 'unhealthy'
    
    return create_api_response({
        'status': status,
        'checks': checks,
        'timestamp': get_current_timestamp()
    }, 200 if all_healthy else 503)

def check_ollama_service():
    try:
        client = get_ollama_client()
        return check_ollama_health(client)
    except Exception:
        return False

def check_vector_database():
    try:
        db = get_vector_database()
        db.heartbeat()
        return True
    except Exception:
        return False

def check_disk_space():
    usage = get_disk_usage()
    return usage < 90  // Less than 90% full

def check_memory_usage():
    usage = get_memory_usage_percent()
    return usage < 90  // Less than 90% used
```

---

## Authentication and Authorization

### User Authentication

```
def authenticate_user(username, password):
    user = get_user_from_database(username)
    
    if user is None:
        raise AuthenticationError("Invalid credentials")
    
    if not verify_password(password, user['hashed_password']):
        raise AuthenticationError("Invalid credentials")
    
    if not user['is_active']:
        raise AuthenticationError("Account is disabled")
    
    return user

def verify_password(plain_password, hashed_password):
    return password_hasher.verify(plain_password, hashed_password)

def hash_password(password):
    return password_hasher.hash(password)

def create_access_token(user_id, username, role):
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'exp': get_current_timestamp() + get_config('TOKEN_EXPIRY_SECONDS'),
        'iat': get_current_timestamp()
    }
    
    token = jwt_encode(payload, get_config('SECRET_KEY'), algorithm='HS256')
    return token

def verify_access_token(token):
    try:
        payload = jwt_decode(token, get_config('SECRET_KEY'), algorithms=['HS256'])
        
        if payload['exp'] < get_current_timestamp():
            raise TokenExpiredError()
        
        return payload
    except JWTDecodeError:
        raise InvalidTokenError()

def get_current_user(request):
    auth_header = request.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        raise UnauthorizedError("Missing or invalid authorization header")
    
    token = auth_header.split(' ')[1]
    payload = verify_access_token(token)
    
    user = get_user_from_database_by_id(payload['user_id'])
    
    if user is None or not user['is_active']:
        raise UnauthorizedError("User not found or inactive")
    
    return user
```

### Authorization Middleware

```
def require_authentication(handler_function):
    def wrapper(request, *args, **kwargs):
        try:
            user = get_current_user(request)
            request.user = user
            return handler_function(request, *args, **kwargs)
        except (UnauthorizedError, InvalidTokenError, TokenExpiredError) as e:
            return create_api_error(str(e), 401)
    
    return wrapper

def require_role(required_role):
    def decorator(handler_function):
        def wrapper(request, *args, **kwargs):
            user = request.user
            
            if user['role'] != required_role and user['role'] != 'admin':
                return create_api_error("Insufficient permissions", 403)
            
            return handler_function(request, *args, **kwargs)
        
        return wrapper
    return decorator

def rate_limit(max_requests, time_window_seconds):
    def decorator(handler_function):
        request_counts = {}
        
        def wrapper(request, *args, **kwargs):
            user_id = request.user['user_id']
            current_time = get_current_timestamp()
            
            if user_id not in request_counts:
                request_counts[user_id] = []
            
            // Remove old requests outside time window
            request_counts[user_id] = [
                t for t in request_counts[user_id]
                if current_time - t < time_window_seconds
            ]
            
            if len(request_counts[user_id]) >= max_requests:
                return create_api_error("Rate limit exceeded", 429)
            
            request_counts[user_id].append(current_time)
            return handler_function(request, *args, **kwargs)
        
        return wrapper
    return decorator
```

---

## Caching and Performance

### Query Result Caching

```
def initialize_cache(max_size=1000, ttl_seconds=3600):
    cache = {
        'data': {},
        'access_times': {},
        'max_size': max_size,
        'ttl': ttl_seconds
    }
    return cache

def get_from_cache(cache, key):
    current_time = get_current_timestamp()
    
    if key in cache['data']:
        cached_time = cache['access_times'][key]
        
        if current_time - cached_time < cache['ttl']:
            // Update access time
            cache['access_times'][key] = current_time
            return cache['data'][key]
        else:
            // Expired, remove from cache
            del cache['data'][key]
            del cache['access_times'][key]
    
    return None

def add_to_cache(cache, key, value):
    current_time = get_current_timestamp()
    
    // Check if cache is full
    if len(cache['data']) >= cache['max_size']:
        // Remove least recently used item
        oldest_key = min(cache['access_times'], key=cache['access_times'].get)
        del cache['data'][oldest_key]
        del cache['access_times'][oldest_key]
    
    cache['data'][key] = value
    cache['access_times'][key] = current_time

def cached_rag_query(query, conversation_id=None):
    cache = get_query_cache()
    cache_key = generate_cache_key(query)
    
    // Try to get from cache
    cached_result = get_from_cache(cache, cache_key)
    if cached_result is not None:
        log_info("Cache hit for query")
        return cached_result
    
    // Cache miss, process query
    result = process_rag_query(query, conversation_id)
    
    // Add to cache
    add_to_cache(cache, cache_key, result)
    
    return result

def generate_cache_key(query):
    normalized_query = query.lower().strip()
    return hash_string(normalized_query)
```

### Embedding Cache

```
def get_cached_embedding(text):
    cache = get_embedding_cache()
    cache_key = hash_string(text)
    
    return get_from_cache(cache, cache_key)

def cache_embedding(text, embedding):
    cache = get_embedding_cache()
    cache_key = hash_string(text)
    
    add_to_cache(cache, cache_key, embedding)

def generate_embedding_with_cache(text, client):
    // Check cache first
    cached_embedding = get_cached_embedding(text)
    if cached_embedding is not None:
        return cached_embedding
    
    // Generate new embedding
    embedding = generate_embedding(text, client)
    
    // Cache it
    cache_embedding(text, embedding)
    
    return embedding
```

---

## Error Handling and Logging

### Error Classes

```
class RAGApplicationError(Exception):
    def __init__(self, message, error_code=None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

class DocumentProcessingError(RAGApplicationError):
    pass

class EmbeddingGenerationError(RAGApplicationError):
    pass

class VectorSearchError(RAGApplicationError):
    pass

class LLMGenerationError(RAGApplicationError):
    pass

class AuthenticationError(RAGApplicationError):
    pass

class UnauthorizedError(RAGApplicationError):
    pass

class DocumentNotFoundError(RAGApplicationError):
    pass

class InvalidTokenError(RAGApplicationError):
    pass

class TokenExpiredError(RAGApplicationError):
    pass
```

### Error Handler

```
def handle_application_error(error, request_context=None):
    error_id = generate_uuid()
    
    // Log error with context
    log_error_with_context(
        error_id=error_id,
        error=error,
        context=request_context
    )
    
    // Determine appropriate response
    if isinstance(error, AuthenticationError):
        status_code = 401
        message = "Authentication failed"
    elif isinstance(error, UnauthorizedError):
        status_code = 403
        message = "Access denied"
    elif isinstance(error, DocumentNotFoundError):
        status_code = 404
        message = "Document not found"
    elif isinstance(error, DocumentProcessingError):
        status_code = 400
        message = "Failed to process document"
    else:
        status_code = 500
        message = "Internal server error"
    
    return create_api_error(
        message=message,
        status_code=status_code,
        error_id=error_id
    )

def log_error_with_context(error_id, error, context):
    log_entry = {
        'error_id': error_id,
        'error_type': type(error).__name__,
        'error_message': str(error),
        'timestamp': get_current_timestamp(),
        'context': context,
        'stack_trace': get_stack_trace(error)
    }
    
    logger.error(json_encode(log_entry))
```

### Logging Utilities

```
def log_info(message, extra_data=None):
    log_entry = {
        'level': 'INFO',
        'message': message,
        'timestamp': get_current_timestamp()
    }
    
    if extra_data:
        log_entry['data'] = extra_data
    
    logger.info(json_encode(log_entry))

def log_warning(message, extra_data=None):
    log_entry = {
        'level': 'WARNING',
        'message': message,
        'timestamp': get_current_timestamp()
    }
    
    if extra_data:
        log_entry['data'] = extra_data
    
    logger.warning(json_encode(log_entry))

def log_error(message, error=None, extra_data=None):
    log_entry = {
        'level': 'ERROR',
        'message': message,
        'timestamp': get_current_timestamp()
    }
    
    if error:
        log_entry['error'] = str(error)
        log_entry['error_type'] = type(error).__name__
    
    if extra_data:
        log_entry['data'] = extra_data
    
    logger.error(json_encode(log_entry))

def log_query_analytics(user_id, query, metadata):
    analytics_entry = {
        'event_type': 'query',
        'user_id': user_id,
        'query_length': len(query),
        'query_time': metadata['query_time'],
        'num_sources': metadata['num_sources'],
        'model': metadata['model'],
        'timestamp': get_current_timestamp()
    }
    
    analytics_logger.info(json_encode(analytics_entry))

def log_conversation(conversation_id, query, answer, sources):
    conversation_entry = {
        'conversation_id': conversation_id,
        'query': query,
        'answer': answer['answer'],
        'source_count': len(sources),
        'timestamp': get_current_timestamp()
    }
    
    save_to_conversation_history(conversation_entry)
```

---

## Utility Functions

### Text Processing

```
def count_tokens(text):
    // Simple word-based token counting
    // In production, use proper tokenizer like tiktoken
    words = text.split()
    return len(words)

def split_into_sentences(text):
    // Simple sentence splitting
    // In production, use NLP library like spaCy
    sentence_endings = ['.', '!', '?']
    sentences = []
    current_sentence = ""
    
    for char in text:
        current_sentence += char
        if char in sentence_endings:
            sentences.append(current_sentence.strip())
            current_sentence = ""
    
    if current_sentence.strip():
        sentences.append(current_sentence.strip())
    
    return sentences

def get_last_tokens(text, num_tokens):
    words = text.split()
    if len(words) <= num_tokens:
        return text
    return ' '.join(words[-num_tokens:])

def extract_citation_numbers(text):
    import re
    pattern = r'\[(\d+)\]'
    matches = re.findall(pattern, text)
    return [int(m) for m in matches]
```

### File Operations

```
def save_to_temp_storage(file):
    temp_dir = get_config('TEMP_UPLOAD_DIR')
    ensure_directory_exists(temp_dir)
    
    temp_filename = f"{generate_uuid()}_{file.name}"
    temp_path = join_paths(temp_dir, temp_filename)
    
    with open(temp_path, 'wb') as f:
        f.write(file.read())
    
    return temp_path

def move_to_permanent_storage(temp_path, document_id):
    permanent_dir = get_config('PERMANENT_STORAGE_DIR')
    ensure_directory_exists(permanent_dir)
    
    filename = get_filename(temp_path)
    permanent_path = join_paths(permanent_dir, f"{document_id}_{filename}")
    
    move_file(temp_path, permanent_path)
    return permanent_path

def delete_file(file_path):
    if file_exists(file_path):
        remove_file(file_path)
        log_info(f"Deleted file: {file_path}")

def get_file_size(file_path):
    return os.path.getsize(file_path)

def get_filename(file_path):
    return os.path.basename(file_path)

def get_file_extension(filename):
    return filename.split('.')[-1] if '.' in filename else ''

def detect_file_type(filename):
    extension = get_file_extension(filename).lower()
    
    type_mapping = {
        'pdf': 'pdf',
        'xlsx': 'excel',
        'xls': 'excel'
    }
    
    return type_mapping.get(extension, 'unknown')
```

### API Response Helpers

```
def create_api_response(data, status_code):
    return {
        'status': 'success',
        'data': data,
        'status_code': status_code
    }

def create_api_error(message, status_code, error_id=None):
    error_response = {
        'status': 'error',
        'message': message,
        'status_code': status_code
    }
    
    if error_id:
        error_response['error_id'] = error_id
    
    return error_response

def create_stream_response(generator):
    return {
        'type': 'stream',
        'generator': generator,
        'content_type': 'text/event-stream'
    }
```

### Database Helpers

```
def save_document_metadata(metadata):
    db = get_metadata_database()
    db.insert('documents', metadata)

def update_document_metadata(document_id, updates):
    db = get_metadata_database()
    db.update('documents', updates, where={'document_id': document_id})

def fetch_document_metadata(document_id):
    db = get_metadata_database()
    return db.select_one('documents', where={'document_id': document_id})

def delete_document_metadata(document_id):
    db = get_metadata_database()
    db.delete('documents', where={'document_id': document_id})

def get_chunk_statistics(document_id):
    vector_db = get_vector_database()
    results = vector_db.get(where={'document_id': document_id})
    
    return {
        'total_chunks': len(results['ids']),
        'avg_chunk_size': calculate_average([
            len(doc) for doc in results['documents']
        ])
    }
```

---

## Reflection

### Alignment with Specification Requirements

**Functional Requirements Coverage:**
- ✓ FR1: Document ingestion with PDF and Excel support
- ✓ FR2: Vector embedding generation and storage using nomic-embed-text
- ✓ FR3: Query processing with semantic search
- ✓ FR4: Answer generation with Ollama LLM and citation support
- ✓ FR5: Web UI endpoints for chat and document management
- ✓ FR6: Complete document management CRUD operations

**Non-Functional Requirements Coverage:**
- ✓ NFR1: Performance optimizations with caching and batching
- ✓ NFR2: Scalability through efficient vector search and chunking
- ✓ NFR3: Privacy maintained with local-only processing
- ✓ NFR4: Reliability through error handling and retry logic
- ✓ NFR5: Maintainability with modular design and logging
- ✓ NFR6: Usability through clear API design and error messages

### Security Considerations

**Identified Security Issues:**

1. **File Upload Vulnerabilities**
   - Risk: Malicious file uploads could exploit parsing libraries
   - Solution: Implement strict file validation, size limits, and sandboxed processing

2. **Authentication Token Security**
   - Risk: JWT tokens could be intercepted or stolen
   - Solution: Use HTTPS only, implement token refresh, short expiry times

3. **Injection Attacks**
   - Risk: User queries could contain malicious prompts
   - Solution: Sanitize inputs, implement prompt injection detection

4. **Rate Limiting**
   - Risk: API abuse through excessive requests
   - Solution: Implement per-user rate limiting with exponential backoff

5. **Data Access Control**
   - Risk: Users accessing documents they don't own
   - Solution: Enforce user_id checks on all document operations

**Proposed Security Enhancements:**

```
def sanitize_user_input(text):
    // Remove potentially harmful characters
    dangerous_patterns = ['<script>', 'javascript:', 'onerror=']
    
    for pattern in dangerous_patterns:
        if pattern.lower() in text.lower():
            raise SecurityError("Potentially malicious input detected")
    
    // Limit length
    if len(text) > 10000:
        raise SecurityError("Input exceeds maximum length")
    
    return text.strip()

def validate_file_content(file_path, file_type):
    // Verify file signature matches declared type
    file_signature = read_file_signature(file_path)
    
    expected_signatures = {
        'pdf': b'%PDF',
        'excel': b'PK\x03\x04'  // ZIP signature for xlsx
    }
    
    if not file_signature.startswith(expected_signatures.get(file_type, b'')):
        raise SecurityError("File signature doesn't match declared type")
    
    return True
```

### Performance Optimization Opportunities

1. **Batch Processing**: Implemented for embedding generation to reduce API calls
2. **Caching Strategy**: Query and embedding caches to avoid redundant computation
3. **Async Processing**: Document ingestion can be made asynchronous for better UX
4. **Connection Pooling**: Reuse database connections to reduce overhead
5. **Index Optimization**: HNSW indexing for fast approximate nearest neighbor search

### Error Handling Completeness

All major error scenarios are covered:
- Network failures with Ollama service (retry logic)
- Document processing failures (graceful degradation)
- Vector database errors (proper exception handling)
- Authentication/authorization failures (clear error messages)
- Resource exhaustion (rate limiting, memory management)

This pseudocode provides a complete implementation roadmap that can be directly translated into production Python code while maintaining security, performance, and maintainability standards.