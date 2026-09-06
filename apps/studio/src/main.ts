import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import App from './App.vue'
import './styles.css'

const app = createApp(App)
app.use(createPinia())
app.use(VueQueryPlugin, { queryClient: new QueryClient() })
app.mount('#app')
