<script setup>
import { ref } from 'vue'

const token = ref('example-only')
const tenant = ref('web-demo')
const question = ref('提前还款需要提前多少天申请？')
const busy = ref(false)
const answer = ref('')
const citations = ref([])
const plan = ref([])
const events = ref([])
const error = ref('')
let controller = null

const sampleArchive = {
  doc_id: 'WEB-CONTRACT-001',
  version: 1,
  title: '虚构贷款合同',
  classification: 'internal',
  acl_roles: ['legal'],
  effective_from: '2026-01-01',
  content: '第七条 提前还款。借款人应提前三十日提交书面申请。\n\n第八条 违约责任。发生违约时，应按合同约定流程通知对方。',
}

function headers() {
  return {
    Authorization: `Bearer ${token.value}`,
    'X-Demo-Tenant': tenant.value,
    'X-Demo-Roles': 'archive_reader,archive_writer,legal',
    'X-Demo-Clearance': 'restricted',
    'Content-Type': 'application/json',
  }
}

async function importSample() {
  error.value = ''
  try {
    const response = await fetch('/v1/archives', { method: 'POST', headers: headers(), body: JSON.stringify(sampleArchive) })
    if (!response.ok) throw new Error(`入库失败：HTTP ${response.status} ${await response.text()}`)
    const data = await response.json()
    events.value.push(`档案已入库：${data.doc_id} v${data.version}${data.idempotent ? '（幂等）' : ''}`)
  } catch (cause) {
    error.value = String(cause)
  }
}

function handleFrame(frame) {
  const lines = frame.split('\n')
  const event = lines.find(line => line.startsWith('event: '))?.slice(7)
  const raw = lines.filter(line => line.startsWith('data: ')).map(line => line.slice(6)).join('\n')
  if (!event || !raw) return
  const data = JSON.parse(raw)
  if (event === 'plan') plan.value = data.steps
  if (event === 'token') answer.value += data.text
  if (event === 'citation') citations.value = data.sources
  if (event === 'error') error.value = data.message
  if (event !== 'token') events.value.push(event)
}

async function ask() {
  if (busy.value) return
  busy.value = true
  answer.value = ''
  citations.value = []
  plan.value = []
  events.value = []
  error.value = ''
  controller = new AbortController()
  try {
    const response = await fetch('/v1/chat/stream', {
      method: 'POST', headers: headers(),
      body: JSON.stringify({ question: question.value, top_k: 3 }), signal: controller.signal,
    })
    if (!response.ok || !response.body) throw new Error(`请求失败：HTTP ${response.status} ${await response.text()}`)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let end = buffer.indexOf('\n\n')
      while (end !== -1) {
        handleFrame(buffer.slice(0, end))
        buffer = buffer.slice(end + 2)
        end = buffer.indexOf('\n\n')
      }
    }
  } catch (cause) {
    if (cause.name !== 'AbortError') error.value = String(cause)
  } finally {
    busy.value = false
    controller = null
  }
}

function stop() {
  controller?.abort()
  events.value.push('用户停止')
}
</script>

<template>
  <main class="shell">
    <header>
      <p class="eyebrow">FINANCIAL AGENT / LOCAL LAB</p>
      <h1>合同与合规档案问答</h1>
      <p>观察 LangGraph 节点事件、引用与前端取消。示例档案为虚构内容。</p>
    </header>

    <section class="panel settings">
      <label>本地演示 Token<input v-model="token" type="password" autocomplete="off" /></label>
      <label>演示租户<input v-model="tenant" /></label>
      <button class="secondary" @click="importSample">导入示例合同</button>
    </section>

    <section class="panel">
      <label>你的问题<textarea v-model="question" rows="3" /></label>
      <div class="actions">
        <button :disabled="busy || !question.trim()" @click="ask">{{ busy ? '处理中…' : '开始提问' }}</button>
        <button class="secondary" :disabled="!busy" @click="stop">停止</button>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>回答</h2>
        <pre class="answer">{{ answer || '先导入示例合同，再开始提问。' }}</pre>
        <h3>档案引用</h3>
        <article v-for="item in citations" :key="item.source_id" class="citation">
          <strong>{{ item.title }} · v{{ item.version }}</strong>
          <small>{{ item.doc_id }} / {{ item.section_path }}</small>
          <p>{{ item.excerpt }}</p>
        </article>
      </div>
      <div class="panel side">
        <h2>执行轨迹</h2>
        <h3>Plan</h3>
        <ol><li v-for="step in plan" :key="step">{{ step }}</li></ol>
        <h3>SSE 事件</h3>
        <ol><li v-for="(event, index) in events" :key="index">{{ event }}</li></ol>
      </div>
    </section>
  </main>
</template>
