const { createApp } = Vue;

const VIDEO_PRESET_ORDER = ['square', 'portrait', 'landscape'];

const VIDEO_PRESETS = {
    square: {
        label: 'Square',
        image: '960x960',
        video: '560x560'
    },
    portrait: {
        label: 'Portrait',
        image: '784x1168',
        video: '464x688'
    },
    landscape: {
        label: 'Landscape',
        image: '1168x784',
        video: '464x688'
    }
};

createApp({
    data() {
        const initial = window.__VIDEO_PAGE_DATA__ || {};
        let sessionImage = null;
        let sessionPrompt = null;
        let sessionResolution = null;

        try {
            const storedImage = sessionStorage.getItem('video_source_image');
            if (storedImage) {
                sessionImage = JSON.parse(storedImage);
                sessionImage = {
                    dataUrl: sessionImage.dataUrl || sessionImage.data_url || null,
                    mimeType: sessionImage.mimeType || sessionImage.mime_type || 'image/png',
                    original_name: sessionImage.originalName || sessionImage.original_name || sessionImage.filename || 'upload.png',
                };
                sessionImage.filename = '';
            }
        } catch (error) {
            console.warn('Unable to parse stored video source image:', error);
            sessionImage = null;
        }

        try {
            sessionPrompt = sessionStorage.getItem('video_source_prompt') || null;
            sessionResolution = sessionStorage.getItem('video_source_resolution') || null;
        } catch (error) {
            sessionPrompt = null;
            sessionResolution = null;
        }

        sessionStorage.removeItem('video_source_image');
        sessionStorage.removeItem('video_source_prompt');
        sessionStorage.removeItem('video_source_resolution');
        const rawResolution = (sessionResolution || initial.resolution || '').toString().toLowerCase();

        let initialOrientation = VIDEO_PRESET_ORDER.find((key) => key === rawResolution);
        if (!initialOrientation) {
            initialOrientation = VIDEO_PRESET_ORDER.find(
                (key) => VIDEO_PRESETS[key].image.toLowerCase() === rawResolution
            );
        }
        if (!initialOrientation) {
            initialOrientation = VIDEO_PRESET_ORDER.find(
                (key) => VIDEO_PRESETS[key].video.toLowerCase() === rawResolution
            );
        }
        if (!initialOrientation) {
            initialOrientation = 'square';
        }

        return {
            videoSourceImage: sessionImage || {
                filename: initial.filename || '',
                subfolder: initial.subfolder || '',
                type: initial.imageType || 'output',
                local_path: initial.localPath || initial.filename || '',
                prompt_id: initial.promptId || ''
            },
            videoPrompt: sessionPrompt !== null ? sessionPrompt : (initial.prompt || ''),
            lastVideoPrompt: sessionPrompt !== null ? sessionPrompt : (initial.prompt || ''),
            selectedOrientation: initialOrientation,
            isGeneratingVideo: false,
            isExtendingVideo: false,
            extendingVideoId: null,
            videoResults: [],
            videoError: null,
            previewMode: 'image',
            enableNSFW: false,
            enableNoSound: false,
            showSettingsModal: false,
            settingsEndpoints: {
                generate: '',
                edit: '',
                video: ''
            },
            settingsError: '',
            settingsSaved: false,
            isSavingSettings: false,
            settingsDirty: false,
            driveAuthenticated: false,
            isUploadingToDrive: false
        };
    },
    computed: {
        imageUrl() {
            if (!this.videoSourceImage) {
                return '';
            }
            if (this.videoSourceImage.dataUrl) {
                return this.videoSourceImage.dataUrl;
            }
            if (!this.videoSourceImage.filename) {
                return '';
            }
            const mediaType = (this.videoSourceImage.type || '').toLowerCase();
            if (mediaType === 'local') {
                const params = new URLSearchParams({ type: 'local' });
                if (this.videoSourceImage.local_path) {
                    params.append('local_path', this.videoSourceImage.local_path);
                }
                return `/api/image/${this.videoSourceImage.filename}?${params.toString()}`;
            }
            const subfolder = this.videoSourceImage.subfolder || '';
            const type = this.videoSourceImage.type || 'output';
            return `/api/image/${this.videoSourceImage.filename}?subfolder=${subfolder}&type=${type}`;
        },
        videoResolutionOptions() {
            return VIDEO_PRESET_ORDER.map((key) => ({
                key,
                label: VIDEO_PRESETS[key].label,
                video: VIDEO_PRESETS[key].video
            }));
        },
        selectedVideoResolution() {
            const preset = VIDEO_PRESETS[this.selectedOrientation];
            return preset ? preset.video : VIDEO_PRESETS.square.video;
        },
        imageAspectRatioPadding() {
            const preset = VIDEO_PRESETS[this.selectedOrientation];
            if (!preset) {
                return '100%';
            }
            const [width, height] = preset.video.split('x').map(Number);
            if (!width || !height) {
                return '100%';
            }
            // padding-bottom percentage = (height / width) * 100
            return `${(height / width) * 100}%`;
        },
        imageAspectMaxWidth() {
            const preset = VIDEO_PRESETS[this.selectedOrientation];
            if (!preset) {
                return '100%';
            }
            const [width] = preset.video.split('x').map(Number);
            if (!width) {
                return '100%';
            }
            return `${width}px`;
        },
        imageContainerStyle() {
            if (this.videoSourceImage && (this.videoSourceImage.filename || this.videoSourceImage.dataUrl)) {
                return {
                    width: this.imageAspectMaxWidth,
                    maxWidth: '100%'
                };
            }
            return {};
        }
    },
    mounted() {
        this.$nextTick(() => {
            const textarea = this.$refs.videoPromptInput;
            if (textarea) {
                textarea.focus();
            }
        });

        this.fetchComfyEndpoint();
        this.checkDriveStatus();
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
        goBack() {
            if (this.isGeneratingVideo) return;
            window.location.href = '/';
        },
        getVideoUrl(media) {
            if (!media || !media.filename) return '';
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
            const params = new URLSearchParams({ type: type || 'output' });
            if (subfolder) {
                params.append('subfolder', subfolder);
            }
            if (media.format) {
                params.append('format', media.format);
            }
            return `/api/image/${media.filename}?${params.toString()}`;
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
        
        async uploadVideoToDrive(video) {
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
                const fileUrl = this.getVideoUrl(video);
                const filename = video.filename || 'generated_video.mp4';
                const mimeType = video.mime_type || 'video/mp4';
                
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
                    alert(`Video uploaded successfully to Google Drive!\n\nView: ${uploadData.web_view_link}`);
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
        async generateVideo() {
            if (this.isGeneratingVideo) {
                return;
            }

            const prompt = (this.videoPrompt || '').trim();
            if (!prompt) {
                this.videoError = 'Please provide a prompt to generate the video.';
                return;
            }
            if (!this.videoSourceImage || (!this.videoSourceImage.filename && !this.videoSourceImage.dataUrl)) {
                this.videoError = 'Source image is missing.';
                return;
            }

            this.isGeneratingVideo = true;
            this.videoError = null;
            this.videoResults = [];

            try {
                const resolution = this.selectedVideoResolution;
                const [widthString, heightString] = resolution.split('x');
                const width = parseInt(widthString, 10) || 560;
                const height = parseInt(heightString, 10) || 560;

                if (this.videoSourceImage.dataUrl) {
                    try {
                        // Para video, siempre subir a 'input' porque el nodo LoadImage busca ahí
                        const uploadResponse = await fetch('/api/upload-image-data', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                data_url: this.videoSourceImage.dataUrl,
                                filename: this.videoSourceImage.original_name || this.videoSourceImage.filename || 'upload.png',
                                mime_type: this.videoSourceImage.mimeType || 'image/png',
                                mode: 'video',
                                image_type: 'input'  // Siempre 'input' para video
                            })
                        });

                        const uploadData = await uploadResponse.json();
                        if (uploadResponse.ok && uploadData.success && uploadData.image) {
                            this.videoSourceImage = {
                                filename: uploadData.image.filename,
                                subfolder: uploadData.image.subfolder || '',
                                type: uploadData.image.type || 'input'
                            };
                        } else {
                            throw new Error(uploadData.error || 'Unable to upload source image.');
                        }
                    } catch (error) {
                        this.videoError = error.message || 'Unable to upload source image.';
                        this.isGeneratingVideo = false;
                        return;
                    }
                }

                const imagePayload = {
                    filename: this.videoSourceImage.filename,
                    subfolder: this.videoSourceImage.subfolder || '',
                    type: this.videoSourceImage.type || 'output'
                };
                if (this.videoSourceImage.local_path) {
                    imagePayload.local_path = this.videoSourceImage.local_path;
                }
                if (this.videoSourceImage.mime_type) {
                    imagePayload.mime_type = this.videoSourceImage.mime_type;
                }
                if (this.videoSourceImage.original_name) {
                    imagePayload.original_name = this.videoSourceImage.original_name;
                }
                if (this.videoSourceImage.prompt_id) {
                    imagePayload.prompt_id = this.videoSourceImage.prompt_id;
                }

                const response = await fetch('/api/generate-video', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        prompt,
                        image: imagePayload,
                        width,
                        height,
                        nsfw: this.enableNSFW,
                        no_sound: this.enableNoSound
                    })
                });

                const data = await response.json();

                if (!response.ok || !data.success) {
                    throw new Error(data.error || 'Failed to generate video');
                }

                if (Array.isArray(data.videos)) {
                    this.videoResults = data.videos.map((video) => ({
                        filename: video?.filename ?? '',
                        subfolder: video?.subfolder ?? '',
                        type: video?.type ?? 'output',
                        format: video?.format ?? 'mp4',
                        local_path: video?.local_path ?? '',
                        prompt_id: video?.prompt_id ?? ''
                    }));
                } else {
                    this.videoResults = [];
                }
                if (this.videoResults.length === 0) {
                    this.videoError = 'Video generation finished but no video was returned.';
                } else {
                    this.lastVideoPrompt = prompt;
                    this.previewMode = 'video';
                }
            } catch (error) {
                console.error('Error generating video:', error);
                this.videoError = error.message || 'Unexpected error generating video.';
            } finally {
                this.isGeneratingVideo = false;
            }
        },

        handleNSFWToggle() {
            if (this.enableNSFW) {
                this.enableNoSound = false;
            }
        },
        async extendVideo(video, index) {
            if (this.isGeneratingVideo || this.isExtendingVideo) {
                return;
            }
            const baseVideo = video || this.videoResults?.[index];
            if (!baseVideo) {
                this.videoError = 'No video available to extend.';
                return;
            }
            if (!this.canExtendVideo(baseVideo)) {
                this.videoError = 'This video cannot be extended.';
                return;
            }

            const prompt = (this.lastVideoPrompt || this.videoPrompt || '').trim();
            if (!prompt) {
                this.videoError = 'Please provide a prompt before extending the video.';
                return;
            }

            const identifier = this.getVideoIdentifier(baseVideo, index);
            this.isExtendingVideo = true;
            this.extendingVideoId = identifier;
            this.videoError = null;

            try {
                const response = await fetch('/api/video/extend', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        prompt,
                        video: {
                            filename: baseVideo.filename,
                            subfolder: baseVideo.subfolder || '',
                            type: baseVideo.type || 'output',
                            local_path: baseVideo.local_path || '',
                            prompt_id: baseVideo.prompt_id || ''
                        }
                    })
                });

                const data = await response.json();
                if (!response.ok || !data.success) {
                    throw new Error(data.error || 'Failed to extend the video');
                }

                const baseRecord = this.normalizeVideoRecord(data.base_video) || baseVideo;
                const extendedRecord = this.normalizeVideoRecord(data.extended_video);
                const mergedRecord = this.normalizeVideoRecord(data.merged_video);

                if (index >= 0 && index < this.videoResults.length) {
                    this.videoResults.splice(index, 1, baseRecord);
                }

                let insertIndex = index >= 0 ? index + 1 : this.videoResults.length;
                if (extendedRecord) {
                    this.videoResults.splice(insertIndex, 0, extendedRecord);
                    insertIndex += 1;
                }
                if (mergedRecord) {
                    this.videoResults.splice(insertIndex, 0, mergedRecord);
                }

                this.lastVideoPrompt = prompt;
                this.previewMode = 'video';
            } catch (error) {
                console.error('Error extending video:', error);
                this.videoError = error.message || 'Unexpected error extending video.';
            } finally {
                this.isExtendingVideo = false;
                this.extendingVideoId = null;
            }
        },
        canExtendVideo(video) {
            if (!video) {
                return false;
            }
            const type = (video.type || '').toLowerCase();
            if (type !== 'local') {
                return false;
            }
            return Boolean(video.local_path || video.filename);
        },
        getVideoIdentifier(video, index) {
            return video?.filename || video?.local_path || `video-${index}`;
        },
        normalizeVideoRecord(record) {
            if (!record) {
                return null;
            }
            return {
                filename: record.filename || '',
                subfolder: record.subfolder || '',
                type: record.type || 'output',
                format: record.format || 'mp4',
                local_path: record.local_path || '',
                prompt_id: record.prompt_id || '',
                mime_type: record.mime_type || '',
                size: record.size ?? null
            };
        }
    }
}).mount('#video-app');

