<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution'
import 'monaco-editor/min/vs/editor/editor.main.css'

const props = defineProps<{ modelValue: string; readOnly?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const container = ref<HTMLElement | null>(null)
let editor: monaco.editor.IStandaloneCodeEditor | undefined
let subscription: monaco.IDisposable | undefined

const globalScope = self as typeof self & { MonacoEnvironment?: { getWorker: () => Worker } }
globalScope.MonacoEnvironment = { getWorker: () => new EditorWorker() }

onMounted(() => {
  if (!container.value) return
  editor = monaco.editor.create(container.value, {
    value: props.modelValue,
    language: 'python',
    theme: 'vs-dark',
    automaticLayout: true,
    fontSize: 12,
    lineHeight: 19,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    renderLineHighlight: 'line',
    readOnly: props.readOnly,
    padding: { top: 10 },
  })
  subscription = editor.onDidChangeModelContent(() => emit('update:modelValue', editor?.getValue() ?? ''))
})

watch(() => props.modelValue, (value) => {
  if (editor && editor.getValue() !== value) editor.setValue(value)
})
watch(() => props.readOnly, (value) => editor?.updateOptions({ readOnly: value }))

onBeforeUnmount(() => {
  subscription?.dispose()
  editor?.dispose()
})
</script>

<template><div ref="container" class="monaco-workspace" data-testid="monaco-workspace" /></template>
