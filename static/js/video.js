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
            }
        } catch (error) {
            console.warn('Unable to parse stored video source image:', error);
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
                type: initial.imageType || 'output'
            },
            videoPrompt: sessionPrompt !== null ? sessionPrompt : (initial.prompt || ''),
            selectedOrientation: initialOrientation,
            isGeneratingVideo: false,
            videoResults: [],
            videoError: null,
            previewMode: 'image'
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
    },
    methods: {
        goBack() {
            if (this.isGeneratingVideo) return;
            window.location.href = '/';
        },
        getVideoUrl(media) {
            if (!media || !media.filename) return '';
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

                if (this.videoSourceImage.dataUrl && !this.videoSourceImage.filename) {
                    try {
                        const uploadResponse = await fetch('/api/upload-image-data', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                data_url: this.videoSourceImage.dataUrl,
                                filename: this.videoSourceImage.filename || this.videoSourceImage.original_name || 'upload.png',
                                mime_type: this.videoSourceImage.mimeType || 'image/png'
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

                const response = await fetch('/api/generate-video', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        prompt,
                        image: this.videoSourceImage,
                        width,
                        height
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
                        format: video?.format ?? 'mp4'
                    }));
                } else {
                    this.videoResults = [];
                }
                if (this.videoResults.length === 0) {
                    this.videoError = 'Video generation finished but no video was returned.';
                } else {
                    this.previewMode = 'video';
                }
            } catch (error) {
                console.error('Error generating video:', error);
                this.videoError = error.message || 'Unexpected error generating video.';
            } finally {
                this.isGeneratingVideo = false;
            }
        }
    }
}).mount('#video-app');

