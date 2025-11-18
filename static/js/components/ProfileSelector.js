// static/js/components/ProfileSelector.js
export const ProfileSelector = {
    template: `
        <div class="profile-selector">
            <button @click="selectProfile('anime')" :class="{ active: selectedProfile === 'anime' }">
                Anime
            </button>
            <button @click="selectProfile('photorealistic')" :class="{ active: selectedProfile === 'photorealistic' }">
                Photorealistic
            </button>
            <button @click="selectProfile('artistic')" :class="{ active: selectedProfile === 'artistic' }">
                Artistic
            </button>
        </div>
    `,
    props: ['initialProfile'],
    emits: ['update:profile'],
    data() {
        return {
            selectedProfile: this.initialProfile
        };
    },
    methods: {
        selectProfile(profile) {
            this.selectedProfile = profile;
            this.$emit('update:profile', this.selectedProfile);
        }
    }
};
