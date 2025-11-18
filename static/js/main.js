import { ProfileSelector } from './components/ProfileSelector.js';
const { createApp } = Vue;

createApp({
    components: {
        ProfileSelector,
    },
    data() {
        return {
            // Sistema de pasos
            steps: [
                { id: 1, name: 'Character', placeholder: 'Describe the character (e.g., "anime girl with blue hair")' },
                { id: 2, name: 'Art-Style', placeholder: 'Specify art style (e.g., "anime style, cel-shaded")' },
                { id: 3, name: 'Character Appearance', placeholder: 'Character appearance details (e.g., "tall, slender, green eyes")' },
                { id: 4, name: 'Clothing', placeholder: 'Describe clothing (e.g., "school uniform, white shirt, blue skirt")' },
                { id: 5, name: 'Expression & Action', placeholder: 'Expression and action (e.g., "smiling, waving hand")' },
                { id: 6, name: 'Camera / Positioning', placeholder: 'Camera angle and positioning (e.g., "close-up, front view")' },
                { id: 7, name: 'Lighting & Effects', placeholder: 'Lighting and effects (e.g., "soft lighting, bokeh background")' },
                { id: 8, name: 'Scene Atmosphere', placeholder: 'Scene atmosphere (e.g., "peaceful morning, cherry blossoms")' },
                { id: 9, name: 'Quality Tag', placeholder: 'Quality tags (e.g., "high quality, detailed")' },
                { id: 10, name: 'Natural-language enrichment', placeholder: 'Additional natural language description (optional)' }
            ],
            currentStep: 0,
            promptParts: {},
            currentInput: '',
            selectedResolution: '960x960',
            selectedSteps: 20, // Pasos de inferencia por defecto
            selectedModel: 'lumina', // Modelo seleccionado (lumina/chroma)
            selectedCheckpoint: '',
            selectedLora: '',
            checkpoints: [],
            loras: [],
            selectedProfile: 'anime',
            generationMode: 'generate', // Modo de generación (generate/edit)
            isGenerating: false,
            modalImage: null,
            messageIdCounter: 0,
            chatMessages: [],
            currentPrompt: '',
            improveWithAI: false,
            isImproving: false,
            flowCompleted: false,
            promptMode: 'direct', // 'interactive' o 'direct'
            directPrompt: '', // Prompt para modo directo
            currentSeed: null, // Seed para modo interactivo (se genera al inicio y se mantiene)
            availableTags: [], // Tags disponibles para la categoría actual
            selectedTags: new Set(), // Tags seleccionados (para ocultarlos)
            displayedTags: [], // Tags mostrados actualmente (máximo 5)
            tagsIndex: 0, // Índice para saber cuántos tags hemos mostrado
            allDisplayedTags: new Set(), // Todos los tags que ya se han mostrado (incluyendo los anteriores)
            tagsVisible: true, // Control de visibilidad de los tags
            isUploadingImage: false, // Estado de carga de imágenes en modo edición
            showSettingsModal: false,
            settingsEndpoints: {
                generate: '',
                edit: '',
                video: ''
            },
            isSavingSettings: false,
            settingsError: '',
            settingsSaved: false,
            settingsDirty: false,
            driveAuthenticated: false,
            isUploadingToDrive: false,
            generationAbortController: null,
            isStoppingGeneration: false
        };
    },
    computed: {
        currentStepInfo() {
            if (this.currentStep >= 0 && this.currentStep < this.steps.length) {
                return this.steps[this.currentStep];
            }
            return null;
        },
        isEditMode() {
            return this.generationMode === 'edit';
        },
        currentPlaceholder() {
            if (this.isFlowComplete && this.selectedProfile === 'anime') {
                return 'Flow completed. Press "+" to start a new prompt';
            }
            if (this.isImproving) {
                return 'Improving with AI...';
            }

            switch (this.selectedProfile) {
                case 'anime':
                    if (this.promptMode === 'direct') {
                        return 'Describe what you want to generate...';
                    }
                    if (this.currentStepInfo) {
                         return `${this.currentStepInfo.name}: ${this.currentStepInfo.placeholder}`;
                    }
                    return 'Type to generate';
                case 'photorealistic':
                    return 'Enter a photorealistic prompt (e.g., "photo of a woman in a red dress, detailed skin texture")';
                case 'artistic':
                    return 'Enter an artistic prompt (e.g., "oil painting of a landscape, style of Van Gogh")';
                default:
                    return 'Type to generate';
            }
        },
        progressPercentage() {
            if (this.currentStep >= 0 && this.currentStep < this.steps.length) {
                return ((this.currentStep + 1) / this.steps.length) * 100;
            }
            return 0;
        },
        isPromptComplete() {
            return this.currentStep >= this.steps.length;
        },
        isFlowComplete() {
            // El flujo está completo cuando se marcó como completado y no estamos generando
            return this.flowCompleted && !this.isGenerating && !this.isImproving;
        },
        modalImageUrl() {
            if (!this.modalImage) return '';
            // Use getMediaUrl to properly handle local images
            return this.getMediaUrl(this.modalImage);
        },
    },
    mounted() {
        // Iniciar en el primer paso
        this.currentStep = 0;
        // Generar seed inicial para modo interactivo
        if (this.promptMode === 'interactive') {
            this.currentSeed = this.generateRandomSeed();
            // Cargar tags para el paso actual
            if (this.currentStepInfo) {
                this.loadTagsForStep(this.currentStepInfo.name);
            }
        }
        this.$nextTick(() => {
            if (this.promptMode === 'interactive' && this.$refs.promptInput) {
                this.$refs.promptInput.focus();
            } else if (this.promptMode === 'direct' && this.$refs.directPromptInput) {
                this.$refs.directPromptInput.focus();
            }
            
        });
        
        // Cerrar modal con Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                if (this.showSettingsModal) {
                    this.closeSettings();
                } else {
                    this.closeModal();
                }
            }
        });

        this.fetchComfyEndpoint();
        this.fetchModels();
        this.checkDriveStatus();
        
        // Verificar si viene de autorización exitosa de Drive
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('drive_auth') === 'success') {
            this.checkDriveStatus();
            // Limpiar el parámetro de la URL
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    },
    watch: {
        chatMessages: {
            handler() {
                // Auto-scroll cuando se añaden nuevos mensajes
                this.$nextTick(() => {
                    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                });
            },
            deep: true
        },
        promptMode(newMode) {
            if (newMode === 'interactive') {
                if (this.currentStepInfo) {
                    this.loadTagsForStep(this.currentStepInfo.name);
                }
            } else {
                this.availableTags = [];
                this.selectedTags.clear();
                this.displayedTags = [];
                this.tagsIndex = 0;
            }
        },
        improveWithAI() {
            // No hay nada que hacer aquí para iconos SVG
        },
        currentStep(newStep) {
            // Cargar tags cuando cambia el paso
            if (this.promptMode === 'interactive' && this.currentStepInfo) {
                this.loadTagsForStep(this.currentStepInfo.name);
                // Resetear tags seleccionados al cambiar de paso
                this.selectedTags.clear();
                this.displayedTags = [];
                this.tagsIndex = 0;
            }
        },
        generationMode(newMode, oldMode) {
            const GENERATE_DEFAULT_STEPS = 20;
            const EDIT_DEFAULT_STEPS = 4;

            if (newMode === 'edit') {
                if (this.selectedSteps === GENERATE_DEFAULT_STEPS) {
                    this.selectedSteps = EDIT_DEFAULT_STEPS;
                }
                this.currentPrompt = '';
                this.directPrompt = '';
            } else if (oldMode === 'edit' && this.selectedSteps === EDIT_DEFAULT_STEPS) {
                this.selectedSteps = GENERATE_DEFAULT_STEPS;
            }
        }
    },
    methods: {
        openSettings() {
            this.settingsError = '';
            this.settingsSaved = false;
            this.showSettingsModal = true;
            this.settingsDirty = false;
            this.fetchComfyEndpoint();
        },
        closeSettings() {
            if (this.isSavingSettings) {
                return;
            }
            this.showSettingsModal = false;
            this.settingsError = '';
            this.settingsSaved = false;
            this.settingsDirty = false;
        },
        async fetchComfyEndpoint() {
            try {
                const response = await fetch('/api/settings/comfy-endpoint', {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json'
                    }
                });
                const data = await response.json();
                if (response.ok && data.success) {
                    if (!this.settingsDirty) {
                        this.settingsEndpoints.generate = data.generate || data.url || '';
                        this.settingsEndpoints.edit = data.edit || '';
                        this.settingsEndpoints.video = data.video || '';
                    }
                } else {
                    this.settingsError = data.error || 'Unable to load ComfyUI endpoints.';
                }
            } catch (error) {
                console.error('Error loading ComfyUI endpoints:', error);
                this.settingsError = 'Unexpected error loading endpoints.';
            }
        },
        handleSettingsInput() {
            this.settingsDirty = true;
            this.settingsSaved = false;
        },
        async saveSettings() {
            this.isSavingSettings = true;
            this.settingsError = '';
            this.settingsSaved = false;

            try {
                // Enviar todos los valores, incluso si están vacíos
                const payload = {
                    generate: (this.settingsEndpoints.generate || '').trim(),
                    edit: (this.settingsEndpoints.edit || '').trim(),
                    video: (this.settingsEndpoints.video || '').trim()
                };

                const response = await fetch('/api/settings/comfy-endpoint', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (response.ok && data.success) {
                    this.settingsSaved = true;
                    this.settingsDirty = false;
                    // Actualizar los valores con los que retornó el servidor
                    if (data.generate) this.settingsEndpoints.generate = data.generate;
                    if (data.edit) this.settingsEndpoints.edit = data.edit;
                    if (data.video) this.settingsEndpoints.video = data.video;
                } else {
                    this.settingsError = data.error || 'Unable to update endpoints.';
                }
            } catch (error) {
                console.error('Error saving ComfyUI endpoints:', error);
                this.settingsError = 'Unexpected error updating endpoints.';
            } finally {
                this.isSavingSettings = false;
            }
        },
        // Función helper para limpiar respuestas de la IA (remover markdown, backticks, etc.)
        cleanAIResponse(text) {
            if (!text || !text.trim()) {
                return '';
            }
            
            let cleaned = text.trim();
            
            // Extraer contenido de bloques de código markdown (```...```)
            // Si hay un bloque de código, intentar extraer el contenido interno
            const codeBlockMatch = cleaned.match(/```(?:[\w]*)?\n?([\s\S]*?)\n?```/);
            if (codeBlockMatch && codeBlockMatch[1]) {
                // Usar el contenido dentro del bloque de código
                cleaned = codeBlockMatch[1].trim();
            } else {
                // Remover bloques de código markdown si no hay contenido útil
                cleaned = cleaned.replace(/```[\s\S]*?```/g, '');
            }
            
            // Remover backticks individuales que puedan quedar
            cleaned = cleaned.replace(/`/g, '');
            
            // Remover espacios en blanco excesivos y saltos de línea
            cleaned = cleaned.replace(/\n+/g, ' ').replace(/\s+/g, ' ').trim();
            
            // Si después de limpiar solo quedan comas o está vacío, retornar vacío
            const withoutCommas = cleaned.replace(/,/g, '').trim();
            if (!withoutCommas || withoutCommas.length === 0) {
                return '';
            }
            
            return cleaned;
        },
        
        // Función helper para limpiar tags duplicados y asegurar que termine con coma
        cleanPromptTags(prompt) {
            if (!prompt || !prompt.trim()) {
                return '';
            }
            
            // Dividir por comas y limpiar cada tag
            const tags = prompt.split(',')
                .map(tag => tag.trim())
                .filter(tag => tag.length > 0);
            
            // Eliminar duplicados (case-insensitive)
            const uniqueTags = [];
            const seenTags = new Set();
            
            for (const tag of tags) {
                const lowerTag = tag.toLowerCase();
                if (!seenTags.has(lowerTag)) {
                    seenTags.add(lowerTag);
                    uniqueTags.push(tag);
                }
            }
            
            // Unir con comas y asegurar que termine con coma
            let cleaned = uniqueTags.join(', ');
            if (cleaned && !cleaned.endsWith(',')) {
                cleaned += ',';
            }
            
            return cleaned;
        },
        
        async handleInput() {
            // Modo directo: manejar prompt directo
            if (this.promptMode === 'direct') {
                if (this.isGenerating || this.isImproving) {
                    return;
                }
                
                const directInput = this.directPrompt.trim();
                if (!directInput) {
                    return;
                }
                
                let promptToAdd = directInput;
                
                // Si el mejorador de IA está activado, mejorar el prompt
                if (this.improveWithAI) {
                    this.isImproving = true;
                    try {
                        // Usar el endpoint de conversión a lenguaje natural para mejorar el prompt
                        const improvedResult = await this.convertToNaturalLanguage(directInput);
                        if (improvedResult && improvedResult.trim()) {
                            // Concatenar el prompt original con el mejorado
                            promptToAdd = directInput + ' ' + improvedResult;
                        }
                    } catch (error) {
                        console.error('[DEBUG] Error al mejorar prompt en modo directo:', error);
                    } finally {
                        this.isImproving = false;
                    }
                }
                
                if (this.isEditMode) {
                    this.currentPrompt = promptToAdd.trim();
                } else if (this.currentPrompt && this.currentPrompt.trim()) {
                    // Agregar el nuevo prompt al prompt acumulado
                    this.currentPrompt = (this.currentPrompt.trim() + ' ' + promptToAdd.trim()).trim();
                } else {
                    // Si no hay prompt acumulado, usar el nuevo como inicial
                    this.currentPrompt = promptToAdd.trim();
                }
                
                // Generar imagen con el prompt actual
                await this.generateImages(this.selectedSteps);
                
                // Limpiar solo el textarea (no el currentPrompt) y restaurar el focus para continuar el chat
                this.directPrompt = '';
                this.$nextTick(() => {
                    this.$refs.directPromptInput?.focus();
                });
                return;
            }
            
            // Modo interactivo: continuación del código existente
            const input = this.currentInput.trim();
            
            // Definir variables para detectar el último paso
            const isLastStep = this.currentStep === this.steps.length - 1;
            const isNaturalLanguageStep = this.currentStepInfo?.name === 'Natural-language enrichment';
            
            // Permitir continuar sin input en todos los pasos (solo bloquear si está generando o mejorando)
            if (this.isGenerating || this.isImproving) {
                return;
            }
            
            // Si estamos en proceso de construcción del prompt
            if (this.currentStep < this.steps.length) {
                let finalInput = input;
                
                // Si es el último paso (Natural-language enrichment) y el checkbox está activado,
                // convertir todo el prompt concatenado a lenguaje natural
                if (isLastStep && isNaturalLanguageStep && this.improveWithAI) {
                    console.log('[DEBUG] Último paso detectado. Convirtiendo prompt completo a lenguaje natural.');
                    this.isImproving = true;
                    try {
                        // Construir el prompt actual con tags antes de agregar el input actual
                        const currentTagsPrompt = this.currentPrompt || '';
                        
                        // Si hay input adicional, agregarlo temporalmente
                        const fullTagsPrompt = currentTagsPrompt && input
                            ? (currentTagsPrompt + ' ' + input.trim()).trim()
                            : (currentTagsPrompt || input || '');
                        
                        if (!fullTagsPrompt) {
                            console.warn('[DEBUG] No hay prompt para convertir');
                            this.isImproving = false;
                            return;
                        }
                        
                        console.log('[DEBUG] Convirtiendo prompt de tags a lenguaje natural:', fullTagsPrompt);
                        const naturalLanguageResult = await this.convertToNaturalLanguage(fullTagsPrompt);
                        console.log('[DEBUG] Resultado de conversión a lenguaje natural:', naturalLanguageResult);
                        
                        if (naturalLanguageResult) {
                            // Concatenar el prompt de tags con el prompt en lenguaje natural
                            // Primero el prompt de tags, luego el enriquecido en lenguaje natural
                            if (input && currentTagsPrompt) {
                                // Si hay input adicional, incluirlo en el prompt de tags
                                const finalTagsPrompt = (currentTagsPrompt + ' ' + input.trim()).trim();
                                this.currentPrompt = finalTagsPrompt + ' ' + naturalLanguageResult + ',';
                            } else {
                                // Si no hay input adicional, concatenar el prompt de tags original con el enriquecido
                                this.currentPrompt = fullTagsPrompt + ' ' + naturalLanguageResult + ',';
                            }
                            // Limpiar tags duplicados y asegurar que termine con coma
                            this.currentPrompt = this.cleanPromptTags(this.currentPrompt);
                            finalInput = ''; // No agregar nada más, ya tenemos el prompt completo concatenado
                            console.log('[DEBUG] Prompt concatenado (tags + lenguaje natural):', this.currentPrompt);
                        } else {
                            console.warn('[DEBUG] No se pudo convertir a lenguaje natural, usando tags originales');
                            // Continuar con el flujo normal si falla la conversión
                            if (input && this.currentPrompt) {
                                const separator = this.currentPrompt.trim().endsWith(',') ? ' ' : ', ';
                                this.currentPrompt = (this.currentPrompt.trim() + separator + input.trim()).trim();
                            } else if (input) {
                                this.currentPrompt = input.trim();
                            }
                            // Limpiar tags duplicados
                            this.currentPrompt = this.cleanPromptTags(this.currentPrompt);
                        }
                    } catch (error) {
                        console.error('[DEBUG] Error al convertir a lenguaje natural:', error);
                        // Continuar con el prompt original si hay error
                        if (input && this.currentPrompt) {
                            const separator = this.currentPrompt.trim().endsWith(',') ? ' ' : ', ';
                            this.currentPrompt = (this.currentPrompt.trim() + separator + input.trim()).trim();
                        } else if (input) {
                            this.currentPrompt = input.trim();
                        }
                        // Limpiar tags duplicados
                        this.currentPrompt = this.cleanPromptTags(this.currentPrompt);
                    } finally {
                        this.isImproving = false;
                    }
                }
                // NOTA: Ya no se mejora con IA en los pasos intermedios, solo en el último paso
                
                // Si no es el último paso con conversión a lenguaje natural, agregar el input normal
                if (!(isLastStep && isNaturalLanguageStep && this.improveWithAI && finalInput === '')) {
                    // Guardar la respuesta del paso actual (puede estar vacío)
                    const stepInfo = this.steps[this.currentStep];
                    this.promptParts[stepInfo.name] = finalInput;
                    
                    // Solo agregar el input actual (mejorado o no) al prompt concatenado si tiene contenido válido
                    const trimmedFinalInput = finalInput ? finalInput.trim() : '';
                    // Validar que no esté vacío y que no sea solo comas
                    const isValidInput = trimmedFinalInput && trimmedFinalInput.replace(/,/g, '').trim().length > 0;
                    
                    if (isValidInput) {
                        if (this.currentPrompt) {
                            // Agregar coma si el prompt actual no termina con coma
                            const separator = this.currentPrompt.trim().endsWith(',') ? ' ' : ', ';
                            this.currentPrompt = (this.currentPrompt.trim() + separator + trimmedFinalInput).trim();
                        } else {
                            this.currentPrompt = trimmedFinalInput;
                        }
                        // Asegurar que termine con coma y limpiar duplicados
                        this.currentPrompt = this.cleanPromptTags(this.currentPrompt);
                    }
                    // Si no hay input válido, simplemente continuar sin agregar nada al prompt
                }
                
                // Generar imagen solo en el último paso
                // En pasos intermedios, si el input está vacío, no generar imagen
                // isLastStep ya está declarado arriba, no redeclarar
                const hasValidPrompt = this.currentPrompt && this.currentPrompt.trim().replace(/,/g, '').trim().length > 0;
                const hasInput = finalInput && finalInput.trim().replace(/,/g, '').trim().length > 0;
                
                // Solo generar imagen si:
                // 1. Es el último paso (siempre generar, incluso si está vacío) - usa selectedSteps
                // 2. O si hay un prompt válido Y hay input en pasos intermedios - usa selectedSteps
                if (isLastStep) {
                    // En el último paso, generar siempre, incluso si el prompt está vacío
                    await this.generateImages(this.selectedSteps, null, true);
                } else if (hasValidPrompt && hasInput) {
                    // En pasos intermedios, solo generar si hay input válido
                    // Si no hay input, no generar imagen, solo avanzar al siguiente paso
                    await this.generateImages(this.selectedSteps);
                }
                // Si no es el último paso y no hay input, no generar imagen, solo avanzar
                
                // Avanzar al siguiente paso solo si no es el último
                if (this.currentStep < this.steps.length - 1) {
                    this.currentStep++;
                    this.currentInput = '';
                    // Enfocar el input para el siguiente paso
                    this.$nextTick(() => {
                        this.$refs.promptInput?.focus();
                    });
                } else {
                    // Si llegamos al último paso, desactivar el input y esperar al botón "Nuevo Prompt"
                    this.currentInput = '';
                    // No avanzar ni resetear, el usuario debe presionar "Nuevo Prompt" manualmente
                    this.$nextTick(() => {
                        // Quitar el foco del input para indicar que el flujo terminó
                        this.$refs.promptInput?.blur();
                    });
                }
            }
        },
        
        generateRandomSeed() {
            // Generar una semilla aleatoria entre 0 y 2^32 - 1
            return Math.floor(Math.random() * 4294967296);
        },
        
        async generateImages(steps = 20, seed = null, allowEmptyPrompt = false) {
            // Verificar si hay prompt o si está permitido generar con prompt vacío
            const hasPrompt = this.currentPrompt && this.currentPrompt.trim().replace(/,/g, '').trim().length > 0;
            if (!hasPrompt && !allowEmptyPrompt) {
                return;
            }
            if (this.isGenerating) {
                return;
            }
            
            // Determinar qué seed usar
            let seedToUse = seed;
            if (seedToUse === null) {
                if (this.promptMode === 'interactive') {
                    // En modo interactivo, usar la seed actual o generar una nueva si no existe
                    if (this.currentSeed === null) {
                        this.currentSeed = this.generateRandomSeed();
                    }
                    seedToUse = this.currentSeed;
                } else {
                    // En modo directo, siempre generar una nueva seed
                    seedToUse = this.generateRandomSeed();
                }
            }
            
            // Crear nuevo mensaje de chat con el prompt completo
            const messageId = ++this.messageIdCounter;
            // Usar prompt actual o un prompt por defecto si está vacío y está permitido
            const promptToUse = (this.currentPrompt && this.currentPrompt.trim().replace(/,/g, '').trim().length > 0) 
                ? this.currentPrompt 
                : (allowEmptyPrompt ? 'anime' : '');
            const newMessage = {
                id: messageId,
                userMessage: promptToUse,
                response: {
                    loading: true,
                    images: [],
                    error: null
                }
            };
            
            this.chatMessages.push(newMessage);
            
            this.isGenerating = true;
            this.isStoppingGeneration = false;
            const abortController = new AbortController();
            this.generationAbortController = abortController;
            
            try {
                let lastImagePayload = null;
                if (this.isEditMode) {
                    const lastImage = this.getLastGeneratedImage();
                    if (!lastImage) {
                        const messageIndex = this.chatMessages.findIndex(m => m.id === messageId);
                        if (messageIndex !== -1) {
                            this.chatMessages[messageIndex].response = {
                                loading: false,
                                images: [],
                                error: 'Edit mode requires a previously generated image.'
                            };
                        }
                        return;
                    }
                    if (lastImage.dataUrl) {
                        lastImagePayload = {
                            data_url: lastImage.dataUrl,
                            filename: lastImage.filename || lastImage.original_name || 'attachment.png',
                            mime_type: lastImage.mimeType || 'image/png'
                        };
                    } else {
                        lastImagePayload = {
                            filename: lastImage.filename,
                            subfolder: lastImage.subfolder || '',
                            type: lastImage.type || 'output'
                        };
                        if (lastImage.local_path) {
                            lastImagePayload.local_path = lastImage.local_path;
                        }
                        if (lastImage.mime_type) {
                            lastImagePayload.mime_type = lastImage.mime_type;
                        }
                        if (lastImage.original_name) {
                            lastImagePayload.original_name = lastImage.original_name;
                        }
                        if (lastImage.prompt_id) {
                            lastImagePayload.prompt_id = lastImage.prompt_id;
                        }
                    }
                }

                // Obtener la resolución seleccionada
                const [width, height] = this.selectedResolution.split('x').map(Number);
                
                const response = await fetch('/api/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    signal: abortController.signal,
                    body: JSON.stringify({
                        prompt: promptToUse,
                        width: width,
                        height: height,
                        steps: steps,
                        seed: seedToUse,
                        mode: this.generationMode,
                        model: this.generationMode === 'generate' ? this.selectedModel : null,
                        image: lastImagePayload
                    })
                });
                
                const data = await response.json();
                
                // Actualizar el mensaje con la respuesta
                const messageIndex = this.chatMessages.findIndex(m => m.id === messageId);
                if (messageIndex !== -1) {
                    if (data.success && data.images && data.images.length > 0) {
                        this.chatMessages[messageIndex].response = {
                            loading: false,
                            images: data.images,
                            error: null
                        };
                    } else {
                        this.chatMessages[messageIndex].response = {
                            loading: false,
                            images: [],
                            error: 'Error generating images: ' + (data.error || 'Unknown error')
                        };
                    }
                }
            } catch (error) {
                // Actualizar el mensaje con el error
                const messageIndex = this.chatMessages.findIndex(m => m.id === messageId);
                if (messageIndex !== -1) {
                    const cancelled = error.name === 'AbortError';
                    this.chatMessages[messageIndex].response = {
                        loading: false,
                        images: [],
                        error: cancelled ? 'Generation cancelled by user.' : 'Connection error: ' + error.message
                    };
                }
            } finally {
                if (this.generationAbortController === abortController) {
                    this.generationAbortController = null;
                }
                const wasAborted = abortController.signal.aborted;
                this.isGenerating = false;
                this.isStoppingGeneration = false;
                // Si estamos en el último paso y terminó la generación, marcar el flujo como completado
                if (!wasAborted && this.currentStep === this.steps.length - 1) {
                    this.flowCompleted = true;
                }
            }
        },

        async stopGeneration() {
            if (!this.isGenerating || this.isStoppingGeneration) {
                return;
            }
            this.isStoppingGeneration = true;

            if (this.generationAbortController) {
                this.generationAbortController.abort();
            }

            try {
                await fetch('/api/generate/stop', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ mode: this.generationMode })
                });
            } catch (error) {
                console.error('Error sending stop request:', error);
            } finally {
                this.isStoppingGeneration = false;
            }
        },
        
        resetPromptBuilder() {
            this.currentStep = 0;
            this.promptParts = {};
            this.currentInput = '';
            // No resetear currentPrompt para mantener el historial concatenado
            // Solo resetear si el usuario hace clic en "Nuevo Prompt"
            this.$nextTick(() => {
                this.$refs.promptInput?.focus();
            });
        },
        
        startNewPrompt() {
            this.chatMessages = [];
            this.currentStep = 0;
            this.promptParts = {};
            this.currentInput = '';
            this.currentPrompt = ''; // Resetear el prompt completo para empezar desde cero
            this.flowCompleted = false; // Resetear el flag de flujo completado
            this.directPrompt = ''; // Resetear el prompt directo
            // En modo interactivo, generar una nueva seed al iniciar un nuevo prompt
            if (this.promptMode === 'interactive') {
                this.currentSeed = this.generateRandomSeed();
                // Cargar tags para el paso actual
                if (this.currentStepInfo) {
                    this.loadTagsForStep(this.currentStepInfo.name);
                }
                // Resetear tags seleccionados
                this.selectedTags.clear();
            } else {
                this.currentSeed = null; // En modo directo no mantenemos seed
            }
            this.$nextTick(() => {
                if (this.promptMode === 'interactive' && this.$refs.promptInput) {
                    this.$refs.promptInput.focus();
                } else if (this.promptMode === 'direct' && this.$refs.directPromptInput) {
                    this.$refs.directPromptInput.focus();
                }
            });
        },
        
        togglePromptMode() {
            this.promptMode = this.promptMode === 'interactive' ? 'direct' : 'interactive';
            // Si cambiamos a modo interactivo, generar una nueva seed
            if (this.promptMode === 'interactive') {
                this.currentSeed = this.generateRandomSeed();
            } else {
                this.currentSeed = null; // En modo directo no mantenemos seed
            }
            this.$nextTick(() => {
                if (this.promptMode === 'interactive' && this.$refs.promptInput) {
                    this.$refs.promptInput.focus();
                } else if (this.promptMode === 'direct' && this.$refs.directPromptInput) {
                    this.$refs.directPromptInput.focus();
                }
            });
        },
        
        getMediaUrl(media) {
            if (!media) {
                return '';
            }
            if (media.dataUrl) {
                return media.dataUrl;
            }
            if (!media.filename) {
                return '';
            }
            const mediaType = (media.type || '').toLowerCase();
            if (mediaType === 'local') {
                const params = new URLSearchParams({ type: 'local' });
                if (media.local_path) {
                    params.append('local_path', media.local_path);
                }
                return `/api/image/${media.filename}?${params.toString()}`;
            }
            const subfolder = media.subfolder || '';
            const type = media.type || 'output';
            return `/api/image/${media.filename}?subfolder=${subfolder}&type=${type}`;
        },

        getImageUrl(image) {
            return this.getMediaUrl(image);
        },

        triggerImageUpload() {
            if (this.isGenerating || this.isImproving || this.isUploadingImage) {
                return;
            }
            if (this.$refs.imageUploader) {
                this.$refs.imageUploader.value = '';
                this.$refs.imageUploader.click();
            }
        },

        async handleImageUpload(event) {
            const file = event.target?.files?.[0];
            if (!file) {
                if (event.target) {
                    event.target.value = '';
                }
                return;
            }

            this.isUploadingImage = true;
            const messageId = ++this.messageIdCounter;

            const finalize = () => {
                this.isUploadingImage = false;
                if (event.target) {
                    event.target.value = '';
                }
            };

            try {
                const reader = new FileReader();
                reader.onload = () => {
                    const dataUrl = reader.result;
                    if (!dataUrl) {
                        this.chatMessages.push({
                            id: messageId,
                            userMessage: `Attachment failed: ${file.name}`,
                            response: {
                                loading: false,
                                images: [],
                                error: 'Unable to read image data.'
                            }
                        });
                        finalize();
                        return;
                    }

                    const imagePayload = {
                        filename: file.name || 'attachment.png',
                        dataUrl,
                        mimeType: file.type || 'image/png',
                        isLocal: true,
                        type: 'input'
                    };

                    this.chatMessages.push({
                        id: messageId,
                        userMessage: `Attached image: ${file.name}`,
                        response: {
                            loading: false,
                            images: [imagePayload],
                            error: null
                        }
                    });

                    finalize();
                };

                reader.onerror = () => {
                    this.chatMessages.push({
                        id: messageId,
                        userMessage: `Attachment failed: ${file.name}`,
                        response: {
                            loading: false,
                            images: [],
                            error: 'Unable to read image file.'
                        }
                    });
                    finalize();
                };

                reader.readAsDataURL(file);
            } catch (error) {
                this.chatMessages.push({
                    id: messageId,
                    userMessage: `Attachment failed: ${file.name}`,
                    response: {
                        loading: false,
                        images: [],
                        error: `Error attaching image: ${error.message}`
                    }
                });
                finalize();
            }
        },

        getLastGeneratedImage() {
            for (let i = this.chatMessages.length - 1; i >= 0; i--) {
                const responses = this.chatMessages[i]?.response;
                if (responses && responses.images && responses.images.length > 0) {
                    return responses.images[responses.images.length - 1];
                }
            }
            return null;
        },

        async openVideoGenerator(image) {
            if (!image) {
                return;
            }

            const basePrompt = (this.currentPrompt && this.currentPrompt.trim())
                || (this.directPrompt && this.directPrompt.trim())
                || '';

            if (image.dataUrl) {
                try {
                    const payload = {
                        dataUrl: image.dataUrl,
                        originalName: image.filename || image.original_name || 'upload.png',
                        mimeType: image.mimeType || 'image/png'
                    };
                    sessionStorage.setItem('video_source_image', JSON.stringify(payload));
                    sessionStorage.setItem('video_source_prompt', basePrompt || '');
                    sessionStorage.setItem('video_source_resolution', this.selectedResolution || '');
                } catch (error) {
                    console.warn('Unable to store video source image in sessionStorage:', error);
                    this.chatMessages.push({
                        id: ++this.messageIdCounter,
                        userMessage: 'Video generation error',
                        response: {
                            loading: false,
                            images: [],
                            error: 'Unable to store image for video generation.'
                        }
                    });
                    return;
                }

                const params = new URLSearchParams();
                params.set('source', 'local');
                params.set('resolution', this.selectedResolution);
                if (basePrompt) {
                    params.set('prompt', basePrompt);
                }
                window.location.href = `/video?${params.toString()}`;
                return;
            }

            sessionStorage.removeItem('video_source_image');
            sessionStorage.removeItem('video_source_prompt');
            sessionStorage.removeItem('video_source_resolution');

            if (!image.filename) {
                return;
            }

            const params = new URLSearchParams({
                filename: image.filename,
                subfolder: image.subfolder || '',
                type: image.type || 'output'
            });
            if (image.local_path) {
                params.set('local_path', image.local_path);
            }
            if (image.prompt_id) {
                params.set('prompt_id', image.prompt_id);
            }
            if (basePrompt) {
                params.set('prompt', basePrompt);
            }
            params.set('resolution', this.selectedResolution);
            window.location.href = `/video?${params.toString()}`;
        },
        
        showFullSize(image) {
            this.modalImage = image;
        },
        
        closeModal() {
            this.modalImage = null;
        },
        
        async checkDriveStatus() {
            try {
                const response = await fetch('/api/drive/status');
                const data = await response.json();
                if (data.success) {
                    this.driveAuthenticated = data.authenticated;
                }
            } catch (error) {
                console.error('Error checking Drive status:', error);
            }
        },
        
        async authorizeDrive() {
            try {
                const response = await fetch('/api/drive/authorize');
                const data = await response.json();
                if (data.success && data.authorization_url) {
                    window.location.href = data.authorization_url;
                } else {
                    alert('Failed to authorize Google Drive: ' + (data.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error authorizing Drive:', error);
                alert('Error authorizing Google Drive: ' + error.message);
            }
        },
        
        async uploadToDrive(image) {
            if (this.isUploadingToDrive) {
                return;
            }
            
            // Verificar autenticación
            if (!this.driveAuthenticated) {
                if (confirm('You need to authorize Google Drive first. Authorize now?')) {
                    await this.authorizeDrive();
                }
                return;
            }
            
            this.isUploadingToDrive = true;
            try {
                // Obtener URL del archivo
                let fileUrl;
                if (image.dataUrl) {
                    // Si tiene dataUrl, usarlo directamente (el backend lo manejará)
                    fileUrl = image.dataUrl;
                } else {
                    fileUrl = this.getImageUrl(image);
                }
                
                const filename = image.filename || 'generated_image.png';
                const mimeType = image.mimeType || 'image/png';
                
                const uploadResponse = await fetch('/api/drive/upload', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        file_url: fileUrl,
                        filename: filename,
                        mime_type: mimeType
                    })
                });
                
                const uploadData = await uploadResponse.json();
                
                if (uploadData.success) {
                    alert(`File uploaded successfully to Google Drive!\n\nView: ${uploadData.web_view_link}`);
                } else {
                    if (uploadData.requires_auth) {
                        this.driveAuthenticated = false;
                        if (confirm('Authentication expired. Re-authorize Google Drive?')) {
                            await this.authorizeDrive();
                        }
                    } else {
                        alert('Failed to upload to Google Drive: ' + (uploadData.error || 'Unknown error'));
                    }
                }
            } catch (error) {
                console.error('Error uploading to Drive:', error);
                alert('Error uploading to Google Drive: ' + error.message);
            } finally {
                this.isUploadingToDrive = false;
            }
        },
        
        async loadTagsForStep(categoryName) {
            try {
                // URL encode para manejar caracteres especiales como &
                const encodedCategory = encodeURIComponent(categoryName);
                
                // Resetear todos los tags mostrados al cambiar de paso
                this.allDisplayedTags.clear();
                this.tagsVisible = true; // Mostrar tags al cambiar de paso
                
                const response = await fetch(`/api/tags/${encodedCategory}`);
                const data = await response.json();
                
                if (data.success && data.tags) {
                    this.availableTags = data.tags;
                    console.log('Tags cargados:', data.tags.length);
                    // Resetear tags seleccionados y mostrados al cargar nuevos tags
                    this.selectedTags.clear();
                    this.displayedTags = [];
                    this.tagsIndex = 0;
                    this.updateDisplayedTags();
                } else {
                    this.availableTags = [];
                    this.displayedTags = [];
                    this.tagsIndex = 0;
                }
            } catch (error) {
                console.error('Error loading tags:', error);
                this.availableTags = [];
                this.displayedTags = [];
                this.tagsIndex = 0;
            }
        },
        
        updateDisplayedTags() {
            // Obtener tags disponibles (no seleccionados)
            const visibleTags = this.availableTags.filter(tag => !this.selectedTags.has(tag));
            
            // Llenar displayedTags hasta 5 tags
            while (this.displayedTags.length < 5 && this.tagsIndex < visibleTags.length) {
                const tag = visibleTags[this.tagsIndex];
                this.displayedTags.push(tag);
                // Agregar a la lista de tags ya mostrados
                this.allDisplayedTags.add(tag);
                this.tagsIndex++;
            }
        },
        
        async loadMoreTags() {
            // Agregar los tags actuales a la lista de tags ya mostrados
            this.displayedTags.forEach(tag => {
                this.allDisplayedTags.add(tag);
            });
            
            // Remover todos los tags actuales de displayedTags
            const currentDisplayed = [...this.displayedTags];
            this.displayedTags = [];
            
            try {
                // Obtener la categoría actual
                const categoryName = this.currentStepInfo?.name;
                if (!categoryName || categoryName === 'Natural-language enrichment') {
                    return;
                }
                
                // Construir lista de tags excluidos (todos los que ya se han mostrado)
                const excludedTags = Array.from(this.allDisplayedTags).join(',');
                const encodedCategory = encodeURIComponent(categoryName);
                const encodedExcluded = encodeURIComponent(excludedTags);
                
                // Solicitar nuevos tags excluyendo los ya mostrados
                const response = await fetch(`/api/tags/${encodedCategory}?excluded=${encodedExcluded}`);
                const data = await response.json();
                
                if (data.success && data.tags && data.tags.length > 0) {
                    // Tomar hasta 5 tags nuevos
                    const newTags = data.tags.slice(0, 5);
                    this.displayedTags = newTags;
                    
                    // Agregar los nuevos tags a la lista de mostrados
                    newTags.forEach(tag => {
                        this.allDisplayedTags.add(tag);
                    });
                } else {
                    // Si no hay más tags disponibles, vaciar displayedTags
                    this.displayedTags = [];
                }
            } catch (error) {
                console.error('Error loading more tags:', error);
                // Si hay error, mantener los tags actuales
                this.displayedTags = currentDisplayed;
            }
        },
        
        getTagButtonStyle(index) {
            // Paleta de colores
            const colorPalette = [
                { bg: '#7F5A83', text: '#ffffff', border: '#6b4a6f' }, // Morado/Lavanda
                { bg: '#5a7a65', text: '#ffffff', border: '#4a6a55' }, // Verde más oscuro
                { bg: '#00798c', text: '#ffffff', border: '#006674' }, // Cyan oscuro
                { bg: '#30638e', text: '#ffffff', border: '#275275' }  // Azul oscuro
            ];
            
            // Usar índice para seleccionar color de forma cíclica
            const colorIndex = index % colorPalette.length;
            const selectedColor = colorPalette[colorIndex];
            
            return {
                backgroundColor: selectedColor.bg,
                color: selectedColor.text,
                borderColor: selectedColor.border
            };
        },
        
        truncateTag(tag) {
            // Truncar texto si es muy largo (máximo ~12 caracteres para un botón de 100px)
            const maxLength = 12;
            if (tag && tag.length > maxLength) {
                return tag.substring(0, maxLength - 3) + '...';
            }
            return tag;
        },
        
        selectTag(tag) {
            // Agregar tag al textarea
            if (this.promptMode === 'interactive') {
                // Si ya hay texto, agregar coma y espacio antes
                if (this.currentInput.trim()) {
                    this.currentInput += ', ' + tag;
                } else {
                    this.currentInput = tag;
                }
                
                // Marcar como seleccionado para ocultarlo
                this.selectedTags.add(tag);
                
                // Remover el tag seleccionado de displayedTags
                const tagIndex = this.displayedTags.indexOf(tag);
                if (tagIndex !== -1) {
                    this.displayedTags.splice(tagIndex, 1);
                    
                    // Reemplazar con un nuevo tag disponible
                    const visibleTags = this.availableTags.filter(t => 
                        !this.selectedTags.has(t) && !this.displayedTags.includes(t)
                    );
                    
                    if (visibleTags.length > 0) {
                        // Seleccionar un tag aleatorio de los disponibles
                        const randomIndex = Math.floor(Math.random() * visibleTags.length);
                        this.displayedTags.push(visibleTags[randomIndex]);
                    }
                }
                
                // Focus en el textarea
                this.$nextTick(() => {
                    if (this.$refs.promptInput) {
                        this.$refs.promptInput.focus();
                        // Mover cursor al final
                        const len = this.$refs.promptInput.value.length;
                        this.$refs.promptInput.setSelectionRange(len, len);
                    }
                });
            }
        },
        
        
        async improvePrompt(userPrompt, stepName) {
            try {
                // Validar que el prompt no esté vacío
                if (!userPrompt || !userPrompt.trim()) {
                    console.warn('[DEBUG] improvePrompt: Prompt vacío, no se enviará request');
                    return null;
                }
                
                console.log('[DEBUG] improvePrompt: Enviando request a /api/improve-prompt');
                console.log('[DEBUG] improvePrompt: userPrompt:', userPrompt);
                console.log('[DEBUG] improvePrompt: stepName:', stepName);
                
                const response = await fetch('/api/improve-prompt', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        prompt: userPrompt,
                        step_name: stepName
                    })
                });
                
                console.log('[DEBUG] improvePrompt: Response status:', response.status);
                
                const data = await response.json();
                console.log('[DEBUG] improvePrompt: Response data:', data);
                
                if (data.success && data.improved_prompt) {
                    // Limpiar la respuesta de la IA (remover markdown, backticks, etc.)
                    const cleanedPrompt = this.cleanAIResponse(data.improved_prompt);
                    
                    if (!cleanedPrompt || !cleanedPrompt.trim()) {
                        console.warn('[DEBUG] improvePrompt: Prompt mejorado está vacío después de limpiar');
                        return null;
                    }
                    
                    // Actualizar el input con el prompt mejorado limpio
                    this.currentInput = cleanedPrompt;
                    console.log('[DEBUG] improvePrompt: Prompt mejorado aplicado (limpio):', cleanedPrompt);
                    return cleanedPrompt;
                } else {
                    console.error('[DEBUG] improvePrompt: Error en respuesta:', data.error);
                    return null;
                }
            } catch (error) {
                console.error('[DEBUG] improvePrompt: Error de conexión:', error);
                return null;
            }
        },
        
        async convertToNaturalLanguage(tagsPrompt) {
            try {
                // Validar que el prompt no esté vacío
                if (!tagsPrompt || !tagsPrompt.trim()) {
                    console.warn('[DEBUG] convertToNaturalLanguage: Prompt vacío, no se enviará request');
                    return null;
                }
                
                console.log('[DEBUG] convertToNaturalLanguage: Enviando request a /api/convert-to-natural-language');
                console.log('[DEBUG] convertToNaturalLanguage: tagsPrompt:', tagsPrompt);
                
                const response = await fetch('/api/convert-to-natural-language', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        prompt: tagsPrompt
                    })
                });
                
                console.log('[DEBUG] convertToNaturalLanguage: Response status:', response.status);
                
                const data = await response.json();
                console.log('[DEBUG] convertToNaturalLanguage: Response data:', data);
                
                if (data.success && data.natural_language_prompt) {
                    // Limpiar la respuesta de la IA (remover markdown, backticks, etc.)
                    const cleanedPrompt = this.cleanAIResponse(data.natural_language_prompt);
                    
                    if (!cleanedPrompt || !cleanedPrompt.trim()) {
                        console.warn('[DEBUG] convertToNaturalLanguage: Prompt en lenguaje natural está vacío después de limpiar');
                        return null;
                    }
                    
                    console.log('[DEBUG] convertToNaturalLanguage: Prompt en lenguaje natural recibido (limpio):', cleanedPrompt);
                    return cleanedPrompt;
                } else {
                    console.error('[DEBUG] convertToNaturalLanguage: Error en respuesta:', data.error);
                    return null;
                }
            } catch (error) {
                console.error('[DEBUG] convertToNaturalLanguage: Error de conexión:', error);
                return null;
            }
        },

        async fetchModels() {
            try {
                const response = await fetch('/api/models');
                const data = await response.json();
                if (data.success) {
                    this.checkpoints = data.models.checkpoints;
                    this.loras = data.models.loras;
                    if (this.checkpoints.length > 0) {
                        this.selectedCheckpoint = this.checkpoints[0];
                    }
                }
            } catch (error) {
                console.error('Error fetching models:', error);
            }
        },
        updateProfile(profile) {
            this.selectedProfile = profile;
        },
        async shareOnTwitter(image) {
            const status = prompt("Enter a status for your tweet:", "Generated with #AIContentCreator");
            if (status === null) return;

            try {
                const imageUrl = new URL(this.getImageUrl(image), window.location.origin).href;

                const response = await fetch('/api/social/twitter/upload', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_url: imageUrl, status: status })
                });

                const data = await response.json();

                if (data.success) {
                    alert('Successfully posted to Twitter!');
                } else if (data.requires_auth) {
                    if (confirm("You need to authorize with Twitter first. Authorize now?")) {
                        this.authorizeTwitter();
                    }
                } else {
                    alert(`Error: ${data.error}`);
                }
            } catch (error) {
                alert(`An error occurred: ${error.message}`);
            }
        },

        async authorizeTwitter() {
            try {
                const response = await fetch('/api/social/twitter/authorize');
                const data = await response.json();
                if (data.success && data.authorization_url) {
                    window.location.href = data.authorization_url;
                } else {
                    alert(`Could not start Twitter authorization: ${data.error}`);
                }
            } catch (error) {
                alert(`An error occurred: ${error.message}`);
            }
        }
    }
}).mount('#app');

