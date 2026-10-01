import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Alert, KeyboardAvoidingView, Platform,
  Pressable, ScrollView, StatusBar, StyleSheet, Text, TextInput,
  View, SafeAreaView,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as SecureStore from 'expo-secure-store';

const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const COURSES = ['电磁场与电磁波', '半导体物理', '模拟电子技术', '数字电子技术', '信号与系统', '微电子器件', '集成电路基础', '其他课程'];
const MODES = ['教我知识点', '帮我解题', '考试复习', '错题分析', '资料问答'];
type Tab = 'chat' | 'docs' | 'practice' | 'progress' | 'mistakes';
type Message = { role: 'user' | 'assistant'; content: string; course?: string; created_at?: string };
type Progress = { id: number; course: string; activity: string; title: string; details: string; created_at: string };
type Doc = { id: string; name: string; created_at: string };
type WrongQuestion = { id: number; course: string; question: string; answer: string; created_at: string };

async function request(path: string, token?: string | null, init: RequestInit = {}) {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  const text = await response.text();
  let body: any = {};
  try { body = text ? JSON.parse(text) : {}; } catch { body = { detail: text }; }
  if (!response.ok) {
    const error: any = new Error(body.detail || `请求失败 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return body;
}

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>('chat');
  const [course, setCourse] = useState(COURSES[1]);
  const [mode, setMode] = useState(MODES[0]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [progress, setProgress] = useState<Progress[]>([]);
  const [wrongQuestions, setWrongQuestions] = useState<WrongQuestion[]>([]);
  const [question, setQuestion] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [topic, setTopic] = useState('');
  const [quiz, setQuiz] = useState('');
  const [toolTitle, setToolTitle] = useState('');
  const [toolResult, setToolResult] = useState('');
  const [difficulty, setDifficulty] = useState('中等');
  const [count, setCount] = useState(5);
  const [error, setError] = useState('');

  const refresh = useCallback(async (auth: string) => {
    const [msg, docs, logs, wrong] = await Promise.all([
      request(`/messages?limit=100&course=${encodeURIComponent(course)}`, auth), request('/documents', auth),
      request(`/progress?course=${encodeURIComponent(course)}`, auth), request('/wrong-questions', auth),
    ]);
    setMessages(msg); setDocuments(docs); setProgress(logs); setWrongQuestions(wrong);
  }, [course]);

  useEffect(() => {
    let active = true;
    (async () => {
      const saved = await SecureStore.getItemAsync('study-agent-token');
      if (saved) {
        if (active) setToken(saved);
        try { await refresh(saved); }
        catch (e: any) {
          if (e.status === 401) await SecureStore.deleteItemAsync('study-agent-token');
          else if (active) setError(e.message);
        }
      }
      if (active) setLoading(false);
    })();
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    if (!token) return;
    refresh(token).catch((e) => setError(e.message));
  }, [token, course, refresh]);

  async function login() {
    setBusy(true); setError('');
    try {
      const data = await request('/auth/login', null, { method: 'POST', body: JSON.stringify({ username, password }) });
      await SecureStore.setItemAsync('study-agent-token', data.access_token);
      await refresh(data.access_token);
      setToken(data.access_token);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function logout() {
    await SecureStore.deleteItemAsync('study-agent-token');
    setToken(null); setMessages([]); setDocuments([]); setProgress([]); setWrongQuestions([]);
  }

  async function sendQuestion() {
    const text = question.trim(); if (!text || busy || !token) return;
    setQuestion(''); setBusy(true); setError('');
    const pending = [...messages, { role: 'user' as const, content: text, course }];
    setMessages(pending);
    try {
      const data = await request('/chat', token, { method: 'POST', body: JSON.stringify({ question: text, course, mode, temperature: 0.4 }) });
      setMessages([...pending, { role: 'assistant', content: data.answer, course, created_at: data.created_at }]);
      await refresh(token);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function pickDocuments() {
    if (!token) return;
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain', 'text/markdown'],
        multiple: true, copyToCacheDirectory: true,
      });
      if (result.canceled || !result.assets.length) return;
      setBusy(true); setError('');
      const form = new FormData();
      result.assets.forEach((asset, i) => form.append('files', { uri: asset.uri, name: asset.name || `资料${i + 1}`, type: asset.mimeType || 'application/octet-stream' } as any));
      form.append('course', course);
      const response = await request('/documents', token, { method: 'POST', body: form });
      await refresh(token);
      Alert.alert('资料处理完成', `新增 ${response.added.length} 份，跳过重复 ${response.skipped.length} 份。`);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function removeDocument(id: string) {
    try { await request(`/documents/${id}`, token, { method: 'DELETE' }); await refresh(token!); }
    catch (e: any) { setError(e.message); }
  }

  async function generateQuiz() {
    setBusy(true); setError(''); setQuiz('');
    try {
      const data = await request('/quiz', token, { method: 'POST', body: JSON.stringify({ course, topic, difficulty, count }) });
      setQuiz(data.quiz); await refresh(token!);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function runStudyTool(action: string, title: string, toolTopic = '') {
    setBusy(true); setError(''); setToolTitle(title); setToolResult('');
    try {
      const data = await request('/study-tools', token, { method: 'POST', body: JSON.stringify({ action, course, topic: toolTopic }) });
      setToolResult(data.result); await refresh(token!);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function saveWrongQuestion(message: Message) {
    const index = messages.indexOf(message);
    const previous = messages.slice(0, index).reverse().find((m) => m.role === 'user');
    if (!previous) return;
    try {
      await request('/wrong-questions', token, { method: 'POST', body: JSON.stringify({ course, question: previous.content, answer: message.content }) });
      await refresh(token!); Alert.alert('已保存', '这道题已加入错题本。');
    } catch (e: any) { setError(e.message); }
  }

  async function deleteWrongQuestion(id: number) {
    try { await request(`/wrong-questions/${id}`, token, { method: 'DELETE' }); await refresh(token!); }
    catch (e: any) { setError(e.message); }
  }

  const counts = useMemo(() => ({
    total: progress.length,
    questions: progress.filter((p) => p.activity === '问答').length,
    exercises: progress.filter((p) => p.activity === '练习').length,
  }), [progress]);

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.cyan} size="large" /></View>;
  if (!token) return (
    <SafeAreaView style={styles.loginPage}>
      <StatusBar barStyle="light-content" />
      <View style={styles.brandMark}><Text style={styles.brandGlyph}>μ</Text></View>
      <Text style={styles.loginTitle}>微电子学习助手</Text>
      <Text style={styles.loginSubtitle}>随时学一点，进度都会记住。</Text>
      <View style={styles.loginCard}>
        <Text style={styles.fieldLabel}>账号</Text>
        <TextInput style={styles.input} value={username} onChangeText={setUsername} autoCapitalize="none" placeholder="输入账号" placeholderTextColor={colors.muted} />
        <Text style={styles.fieldLabel}>密码</Text>
        <TextInput style={styles.input} value={password} onChangeText={setPassword} secureTextEntry placeholder="输入密码" placeholderTextColor={colors.muted} onSubmitEditing={login} />
        {!!error && <Text style={styles.error}>{error}</Text>}
        <PrimaryButton title={busy ? '正在登录…' : '登录学习'} onPress={login} disabled={busy || !username || !password} />
      </View>
      <Text style={styles.loginHint}>请使用部署时配置的个人账号登录</Text>
    </SafeAreaView>
  );

  return (
    <SafeAreaView style={styles.page}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.topBar}>
        <View><Text style={styles.eyebrow}>MICROELECTRONICS · AI STUDY</Text><Text style={styles.appTitle}>学习助手</Text></View>
        <Pressable style={styles.logoutButton} onPress={logout}><Text style={styles.logoutText}>退出</Text></Pressable>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.courseStrip}>
        {COURSES.map((item) => <Pressable key={item} onPress={() => setCourse(item)} style={[styles.courseChip, course === item && styles.courseChipActive]}><Text style={[styles.courseChipText, course === item && styles.courseChipTextActive]}>{item}</Text></Pressable>)}
      </ScrollView>
      {error ? <Pressable style={styles.errorBanner} onPress={() => setError('')}><Text style={styles.error}>{error}　×</Text></Pressable> : null}

      <View style={styles.content}>
        {tab === 'chat' && <ChatScreen messages={messages} busy={busy} question={question} setQuestion={setQuestion} sendQuestion={sendQuestion} saveWrong={saveWrongQuestion} mode={mode} setMode={setMode} />}
        {tab === 'docs' && <DocsScreen documents={documents} busy={busy} onPick={pickDocuments} onDelete={removeDocument} onTool={runStudyTool} resultTitle={toolTitle} result={toolResult} />}
        {tab === 'practice' && <PracticeScreen topic={topic} setTopic={setTopic} difficulty={difficulty} setDifficulty={setDifficulty} count={count} setCount={setCount} quiz={quiz} busy={busy} onGenerate={generateQuiz} onFramework={() => runStudyTool('framework', '知识框架', topic)} resultTitle={toolTitle} result={toolResult} />}
        {tab === 'progress' && <ProgressScreen progress={progress} counts={counts} course={course} />}
        {tab === 'mistakes' && <MistakesScreen items={wrongQuestions} onDelete={deleteWrongQuestion} onAnalyze={() => runStudyTool('weak_points', '薄弱点分析')} busy={busy} resultTitle={toolTitle} result={toolResult} />}
      </View>
      <View style={styles.tabBar}>
        <TabItem label="AI 老师" glyph="✦" active={tab === 'chat'} onPress={() => setTab('chat')} />
        <TabItem label="资料" glyph="▤" active={tab === 'docs'} onPress={() => setTab('docs')} badge={documents.length} />
        <TabItem label="练习" glyph="✓" active={tab === 'practice'} onPress={() => setTab('practice')} />
        <TabItem label="进度" glyph="↗" active={tab === 'progress'} onPress={() => setTab('progress')} />
        <TabItem label="错题" glyph="⌁" active={tab === 'mistakes'} onPress={() => setTab('mistakes')} badge={wrongQuestions.length} />
      </View>
    </SafeAreaView>
  );
}

function ChatScreen({ messages, busy, question, setQuestion, sendQuestion, saveWrong, mode, setMode }: any) {
  return <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={8}>
    <View style={styles.sectionHeading}><View><Text style={styles.screenTitle}>AI 老师</Text><Text style={styles.screenSub}>把难懂的概念讲清楚</Text></View><Text style={styles.onlineDot}>● 在线</Text></View>
    <ScrollView style={styles.flex} contentContainerStyle={styles.chatList} keyboardShouldPersistTaps="handled">
      {!messages.length && <View style={styles.welcomeCard}><Text style={styles.welcomeOrb}>μ</Text><Text style={styles.welcomeTitle}>今天想学点什么？</Text><Text style={styles.welcomeBody}>问概念、发题目，或让我根据上传资料讲解。</Text><View style={styles.suggestionRow}><Text style={styles.suggestion}>PN 结的耗尽区是什么？</Text></View><View style={styles.suggestionRow}><Text style={styles.suggestion}>解释一下麦克斯韦方程组</Text></View></View>}
      {messages.map((message: Message, i: number) => <View key={`${i}-${message.role}`} style={[styles.messageRow, message.role === 'user' && styles.messageRowUser]}><View style={[styles.messageBubble, message.role === 'user' ? styles.userBubble : styles.aiBubble]}><Text style={[styles.messageText, message.role === 'user' && styles.userMessageText]}>{message.content}</Text></View>{message.role === 'assistant' && <Pressable onPress={() => saveWrong(message)} style={styles.saveWrong}><Text style={styles.saveWrongText}>＋ 加入错题本</Text></Pressable>}</View>)}
      {busy && <ActivityIndicator style={{ alignSelf: 'flex-start', margin: 10 }} color={colors.cyan} />}
    </ScrollView>
    <View style={styles.modeStrip}>{MODES.map((m) => <Pressable key={m} style={[styles.modeChip, m === mode && styles.modeChipActive]} onPress={() => setMode(m)}><Text style={[styles.modeText, m === mode && styles.modeTextActive]}>{m}</Text></Pressable>)}</View>
    <View style={styles.composer}><TextInput style={styles.composerInput} value={question} onChangeText={setQuestion} multiline placeholder="输入问题，开始学习…" placeholderTextColor={colors.muted} /><Pressable onPress={sendQuestion} disabled={busy || !question.trim()} style={[styles.sendButton, (busy || !question.trim()) && styles.disabled]}><Text style={styles.sendGlyph}>↑</Text></Pressable></View>
  </KeyboardAvoidingView>;
}

function DocsScreen({ documents, busy, onPick, onDelete, onTool, resultTitle, result }: any) {
  return <ScrollView contentContainerStyle={styles.screenPad}>
    <Text style={styles.screenTitle}>学习资料</Text><Text style={styles.screenSub}>上传后可让 AI 根据资料回答问题</Text>
    <Pressable onPress={onPick} disabled={busy} style={styles.uploadCard}><Text style={styles.uploadIcon}>＋</Text><Text style={styles.uploadTitle}>{busy ? '正在处理资料…' : '选择资料文件'}</Text><Text style={styles.uploadSub}>PDF · Word · TXT · Markdown，单个文件不超过 25 MB</Text></Pressable>
    <Text style={styles.listHeading}>已保存的资料 <Text style={styles.listCount}>{documents.length}</Text></Text>
    {!documents.length ? <EmptyState title="还没有学习资料" body="上传讲义或笔记，之后就能随时提问。" /> : documents.map((doc: Doc) => <View key={doc.id} style={styles.docCard}><View style={styles.fileIcon}><Text style={styles.fileIconText}>PDF</Text></View><View style={styles.docInfo}><Text style={styles.docName} numberOfLines={2}>{doc.name}</Text><Text style={styles.docMeta}>{new Date(doc.created_at).toLocaleDateString()}</Text></View><Pressable onPress={() => onDelete(doc.id)} hitSlop={10}><Text style={styles.deleteGlyph}>×</Text></Pressable></View>)}
    {!!documents.length && <><Text style={styles.listHeading}>资料智能处理</Text><View style={styles.toolButtons}>{[['summary', '总结资料'], ['key_points', '提取重点'], ['flashcards', '生成闪卡']].map(([action, title]) => <Pressable key={action} style={styles.toolButton} disabled={busy} onPress={() => onTool(action, title)}><Text style={styles.toolButtonText}>{busy ? '处理中…' : title}</Text></Pressable>)}</View></>}
    {!!result && <View style={styles.resultCard}><Text style={styles.listHeading}>{resultTitle}</Text><Text style={styles.resultText}>{result}</Text></View>}
    <Text style={styles.privacyNote}>文件内容保存在你的私有学习空间中。</Text>
  </ScrollView>;
}

function PracticeScreen({ topic, setTopic, difficulty, setDifficulty, count, setCount, quiz, busy, onGenerate, onFramework, resultTitle, result }: any) {
  return <ScrollView contentContainerStyle={styles.screenPad}>
    <Text style={styles.screenTitle}>智能练习</Text><Text style={styles.screenSub}>按当前课程生成有解析的练习题</Text>
    <View style={styles.formCard}><Text style={styles.fieldLabel}>知识点</Text><TextInput style={styles.input} value={topic} onChangeText={setTopic} placeholder="例如：PN 结、运算放大器" placeholderTextColor={colors.muted} />
      <Text style={styles.fieldLabel}>难度</Text><View style={styles.optionRow}>{['基础', '中等', '较难', '压轴'].map((item) => <Pressable key={item} onPress={() => setDifficulty(item)} style={[styles.option, difficulty === item && styles.optionActive]}><Text style={[styles.optionText, difficulty === item && styles.optionTextActive]}>{item}</Text></Pressable>)}</View>
      <Text style={styles.fieldLabel}>题目数量：{count}</Text><View style={styles.optionRow}>{[3, 5, 8, 10].map((n) => <Pressable key={n} onPress={() => setCount(n)} style={[styles.option, count === n && styles.optionActive]}><Text style={[styles.optionText, count === n && styles.optionTextActive]}>{n} 道</Text></Pressable>)}</View>
      <PrimaryButton title={busy ? '正在出题…' : '生成练习题'} onPress={onGenerate} disabled={busy} />
      <Pressable onPress={onFramework} disabled={busy} style={styles.secondaryButton}><Text style={styles.secondaryButtonText}>生成知识框架</Text></Pressable>
    </View>
    {quiz ? <View style={styles.resultCard}><Text style={styles.listHeading}>本次练习</Text><Text style={styles.resultText}>{quiz}</Text></View> : <EmptyState title="开始一次针对性练习" body="生成的练习会结合你上传的资料，并记录在学习进度里。" />}
    {!!result && <View style={styles.resultCard}><Text style={styles.listHeading}>{resultTitle}</Text><Text style={styles.resultText}>{result}</Text></View>}
  </ScrollView>;
}

function ProgressScreen({ progress, counts, course }: any) {
  return <ScrollView contentContainerStyle={styles.screenPad}>
    <Text style={styles.screenTitle}>学习进度</Text><Text style={styles.screenSub}>{course} · 学习记录会在登录后同步</Text>
    <View style={styles.statsRow}><StatCard value={counts.total} label="学习活动" /><StatCard value={counts.questions} label="AI 问答" /><StatCard value={counts.exercises} label="练习生成" /></View>
    <Text style={styles.listHeading}>最近活动</Text>
    {!progress.length ? <EmptyState title="记录从第一次学习开始" body="提问、上传资料或生成练习，都会自动记录到这里。" /> : progress.map((item: Progress) => <View key={item.id} style={styles.activityRow}><View style={styles.activityDot}><Text style={styles.activityGlyph}>{item.activity === '问答' ? '✦' : item.activity === '练习' ? '✓' : '▤'}</Text></View><View style={styles.activityText}><Text style={styles.activityTitle}>{item.activity}</Text><Text style={styles.activityDetail} numberOfLines={2}>{item.title}</Text><Text style={styles.activityTime}>{new Date(item.created_at).toLocaleString()}</Text></View></View>)}
  </ScrollView>;
}

function MistakesScreen({ items, onDelete, onAnalyze, busy, resultTitle, result }: any) {
  return <ScrollView contentContainerStyle={styles.screenPad}><Text style={styles.screenTitle}>错题本</Text><Text style={styles.screenSub}>把重要问题收好，之后再复习</Text>
    {!items.length ? <EmptyState title="错题本还是空的" body="在 AI 老师回答下方点“加入错题本”，即可保存题目和解析。" /> : <><PrimaryButton title={busy ? '正在分析…' : '分析薄弱点'} onPress={onAnalyze} disabled={busy} />{items.map((item: WrongQuestion) => <View key={item.id} style={styles.mistakeCard}><View style={styles.mistakeTop}><Text style={styles.mistakeCourse}>{item.course}</Text><Pressable onPress={() => onDelete(item.id)}><Text style={styles.deleteGlyph}>×</Text></Pressable></View><Text style={styles.mistakeQuestion}>{item.question}</Text><Text style={styles.answerLabel}>AI 分析</Text><Text style={styles.mistakeAnswer}>{item.answer}</Text></View>)}</>}
    {!!result && <View style={styles.resultCard}><Text style={styles.listHeading}>{resultTitle}</Text><Text style={styles.resultText}>{result}</Text></View>}
  </ScrollView>;
}

function EmptyState({ title, body }: { title: string; body: string }) { return <View style={styles.empty}><Text style={styles.emptyGlyph}>⌁</Text><Text style={styles.emptyTitle}>{title}</Text><Text style={styles.emptyBody}>{body}</Text></View>; }
function PrimaryButton({ title, onPress, disabled }: { title: string; onPress: () => void; disabled?: boolean }) { return <Pressable onPress={onPress} disabled={disabled} style={[styles.primaryButton, disabled && styles.disabled]}><Text style={styles.primaryButtonText}>{title}</Text></Pressable>; }
function StatCard({ value, label }: { value: number; label: string }) { return <View style={styles.statCard}><Text style={styles.statValue}>{value}</Text><Text style={styles.statLabel}>{label}</Text></View>; }
function TabItem({ label, glyph, active, onPress, badge }: any) { return <Pressable onPress={onPress} style={styles.tabItem}><Text style={[styles.tabGlyph, active && styles.tabActive]}>{glyph}{badge ? <Text style={styles.badge}> {badge}</Text> : null}</Text><Text style={[styles.tabLabel, active && styles.tabActive]}>{label}</Text></Pressable>; }

const colors = { ink: '#17243C', navy: '#101B32', cyan: '#19B6AA', mint: '#DDF5F1', paper: '#F5F7FA', white: '#FFFFFF', muted: '#8490A3', line: '#E7EBF0', red: '#C94D5A', softBlue: '#EAF0FF' };
const styles = StyleSheet.create({
  flex: { flex: 1 }, center: { flex: 1, backgroundColor: colors.navy, alignItems: 'center', justifyContent: 'center' },
  loginPage: { flex: 1, backgroundColor: colors.navy, paddingHorizontal: 25, justifyContent: 'center' }, brandMark: { width: 66, height: 66, borderRadius: 22, backgroundColor: colors.cyan, alignItems: 'center', justifyContent: 'center', marginBottom: 22 }, brandGlyph: { color: colors.white, fontSize: 40, fontWeight: '700' }, loginTitle: { color: colors.white, fontSize: 30, fontWeight: '800', letterSpacing: 0.2 }, loginSubtitle: { color: '#B2BED0', fontSize: 15, marginTop: 9, marginBottom: 32 }, loginCard: { backgroundColor: '#1B2941', borderRadius: 24, padding: 22 }, loginHint: { color: '#8E9BB0', fontSize: 12, textAlign: 'center', marginTop: 18 },
  page: { flex: 1, backgroundColor: colors.paper }, topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: 7, paddingBottom: 14 }, eyebrow: { fontSize: 9, fontWeight: '700', letterSpacing: 1.1, color: colors.cyan }, appTitle: { fontSize: 24, fontWeight: '800', color: colors.ink, marginTop: 3 }, logoutButton: { paddingHorizontal: 14, paddingVertical: 9, borderRadius: 15, backgroundColor: colors.white }, logoutText: { color: colors.muted, fontWeight: '600', fontSize: 13 },
  courseStrip: { paddingHorizontal: 16, paddingBottom: 14, gap: 8 }, courseChip: { borderRadius: 16, paddingHorizontal: 13, paddingVertical: 9, backgroundColor: colors.white, borderWidth: 1, borderColor: colors.line }, courseChipActive: { backgroundColor: colors.navy, borderColor: colors.navy }, courseChipText: { fontSize: 12, color: '#647189', fontWeight: '600' }, courseChipTextActive: { color: colors.white },
  content: { flex: 1 }, sectionHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: 3, paddingBottom: 12 }, screenTitle: { color: colors.ink, fontSize: 23, fontWeight: '800' }, screenSub: { color: colors.muted, fontSize: 13, marginTop: 4, marginBottom: 19 }, onlineDot: { color: colors.cyan, fontSize: 12, fontWeight: '700' }, screenPad: { paddingHorizontal: 19, paddingTop: 7, paddingBottom: 32 },
  chatList: { paddingHorizontal: 18, paddingBottom: 12, flexGrow: 1 }, welcomeCard: { backgroundColor: colors.white, borderRadius: 22, padding: 20, marginTop: 13, marginBottom: 18, borderWidth: 1, borderColor: colors.line }, welcomeOrb: { width: 42, height: 42, borderRadius: 14, backgroundColor: colors.mint, color: colors.cyan, fontSize: 29, lineHeight: 42, textAlign: 'center', overflow: 'hidden', fontWeight: '700', marginBottom: 17 }, welcomeTitle: { color: colors.ink, fontSize: 19, fontWeight: '800' }, welcomeBody: { color: colors.muted, fontSize: 13, lineHeight: 20, marginTop: 6, marginBottom: 13 }, suggestionRow: { paddingVertical: 10, borderTopWidth: 1, borderColor: colors.line }, suggestion: { color: '#50617A', fontSize: 13 }, messageRow: { alignItems: 'flex-start', marginVertical: 6 }, messageRowUser: { alignItems: 'flex-end' }, messageBubble: { maxWidth: '91%', borderRadius: 18, paddingHorizontal: 15, paddingVertical: 12 }, aiBubble: { backgroundColor: colors.white, borderBottomLeftRadius: 5, borderWidth: 1, borderColor: colors.line }, userBubble: { backgroundColor: colors.navy, borderBottomRightRadius: 5 }, messageText: { color: colors.ink, fontSize: 14, lineHeight: 22 }, userMessageText: { color: colors.white }, saveWrong: { padding: 7 }, saveWrongText: { color: colors.cyan, fontSize: 11, fontWeight: '700' }, modeStrip: { flexDirection: 'row', gap: 6, paddingHorizontal: 12, paddingVertical: 8 }, modeChip: { borderRadius: 13, paddingHorizontal: 9, paddingVertical: 7, backgroundColor: colors.white }, modeChipActive: { backgroundColor: colors.mint }, modeText: { fontSize: 10, color: '#6C7890' }, modeTextActive: { color: '#117E77', fontWeight: '700' }, composer: { flexDirection: 'row', alignItems: 'flex-end', marginHorizontal: 14, marginBottom: 9, padding: 7, paddingLeft: 14, borderWidth: 1, borderColor: colors.line, borderRadius: 20, backgroundColor: colors.white }, composerInput: { flex: 1, color: colors.ink, fontSize: 14, maxHeight: 100, paddingTop: 9, paddingBottom: 8 }, sendButton: { width: 39, height: 39, backgroundColor: colors.cyan, borderRadius: 14, alignItems: 'center', justifyContent: 'center' }, sendGlyph: { color: colors.white, fontSize: 22, fontWeight: '700', marginTop: -2 }, disabled: { opacity: 0.48 },
  tabBar: { flexDirection: 'row', justifyContent: 'space-around', paddingTop: 9, paddingBottom: Platform.OS === 'ios' ? 7 : 13, backgroundColor: colors.white, borderTopWidth: 1, borderColor: colors.line }, tabItem: { alignItems: 'center', justifyContent: 'center', minWidth: 53 }, tabGlyph: { fontSize: 19, color: '#98A2B1', height: 23 }, tabLabel: { fontSize: 10, color: '#98A2B1', marginTop: 3, fontWeight: '600' }, tabActive: { color: colors.cyan }, badge: { fontSize: 9, color: colors.cyan, fontWeight: '800' },
  uploadCard: { backgroundColor: colors.navy, borderRadius: 21, padding: 21, alignItems: 'center', marginBottom: 25 }, uploadIcon: { color: colors.cyan, fontSize: 31, fontWeight: '300' }, uploadTitle: { color: colors.white, fontSize: 16, fontWeight: '800', marginTop: 5 }, uploadSub: { color: '#B1BDCF', fontSize: 11, textAlign: 'center', marginTop: 6 }, listHeading: { color: colors.ink, fontSize: 15, fontWeight: '800', marginBottom: 11, marginTop: 12 }, listCount: { color: colors.cyan }, docCard: { flexDirection: 'row', alignItems: 'center', padding: 13, borderRadius: 17, backgroundColor: colors.white, marginBottom: 9 }, fileIcon: { width: 42, height: 45, backgroundColor: colors.softBlue, borderRadius: 12, alignItems: 'center', justifyContent: 'center' }, fileIconText: { color: '#5B75B7', fontSize: 10, fontWeight: '800' }, docInfo: { flex: 1, marginHorizontal: 12 }, docName: { color: colors.ink, fontSize: 13, fontWeight: '700' }, docMeta: { color: colors.muted, fontSize: 11, marginTop: 5 }, deleteGlyph: { color: '#A5AEBB', fontSize: 24, paddingHorizontal: 5 }, privacyNote: { color: colors.muted, fontSize: 11, textAlign: 'center', marginTop: 15 },
  toolButtons: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 }, toolButton: { backgroundColor: colors.mint, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 11 }, toolButtonText: { color: '#117E77', fontSize: 11, fontWeight: '800' }, secondaryButton: { borderColor: '#435068', borderWidth: 1, borderRadius: 14, paddingVertical: 13, alignItems: 'center', marginTop: 8 }, secondaryButtonText: { color: '#D7DFEB', fontWeight: '700', fontSize: 13 },
  fieldLabel: { color: '#D5DCEA', fontSize: 12, fontWeight: '700', marginBottom: 7, marginTop: 8 }, input: { backgroundColor: '#25334B', borderRadius: 13, paddingHorizontal: 13, paddingVertical: 13, color: colors.white, fontSize: 14, marginBottom: 9 }, primaryButton: { backgroundColor: colors.cyan, borderRadius: 14, paddingVertical: 14, alignItems: 'center', marginTop: 12 }, primaryButtonText: { color: colors.white, fontSize: 14, fontWeight: '800' }, formCard: { backgroundColor: colors.navy, borderRadius: 21, padding: 17, marginBottom: 20 }, optionRow: { flexDirection: 'row', gap: 7, marginBottom: 6 }, option: { flex: 1, paddingVertical: 10, alignItems: 'center', borderWidth: 1, borderColor: '#435068', borderRadius: 12 }, optionActive: { backgroundColor: colors.mint, borderColor: colors.mint }, optionText: { color: '#D7DFEB', fontSize: 11, fontWeight: '600' }, optionTextActive: { color: '#117E77', fontWeight: '800' }, resultCard: { backgroundColor: colors.white, borderRadius: 18, padding: 16, marginTop: 8 }, resultText: { color: '#37445A', fontSize: 14, lineHeight: 23 },
  statsRow: { flexDirection: 'row', gap: 8, marginBottom: 23 }, statCard: { flex: 1, backgroundColor: colors.white, borderRadius: 17, padding: 13, borderWidth: 1, borderColor: colors.line }, statValue: { color: colors.ink, fontSize: 25, fontWeight: '800' }, statLabel: { color: colors.muted, fontSize: 10, marginTop: 5 }, activityRow: { flexDirection: 'row', paddingVertical: 13, borderBottomWidth: 1, borderColor: colors.line }, activityDot: { width: 36, height: 36, backgroundColor: colors.mint, borderRadius: 13, alignItems: 'center', justifyContent: 'center', marginRight: 11 }, activityGlyph: { color: colors.cyan, fontWeight: '800' }, activityText: { flex: 1 }, activityTitle: { color: colors.ink, fontSize: 13, fontWeight: '800' }, activityDetail: { color: '#59677E', fontSize: 12, marginTop: 3 }, activityTime: { color: colors.muted, fontSize: 10, marginTop: 5 }, empty: { alignItems: 'center', paddingHorizontal: 25, paddingVertical: 27 }, emptyGlyph: { color: '#B7C4D2', fontSize: 32, marginBottom: 8 }, emptyTitle: { color: colors.ink, fontWeight: '800', fontSize: 14 }, emptyBody: { color: colors.muted, fontSize: 12, lineHeight: 19, textAlign: 'center', marginTop: 6 },
  mistakeCard: { backgroundColor: colors.white, borderRadius: 17, padding: 15, marginBottom: 10 }, mistakeTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, mistakeCourse: { color: colors.cyan, fontSize: 11, fontWeight: '800' }, mistakeQuestion: { color: colors.ink, fontSize: 14, lineHeight: 22, fontWeight: '700', marginVertical: 10 }, answerLabel: { color: colors.muted, fontSize: 10, fontWeight: '800', marginBottom: 4 }, mistakeAnswer: { color: '#536176', fontSize: 12, lineHeight: 19 }, error: { color: '#F49AA4', fontSize: 12, lineHeight: 18, marginVertical: 8 }, errorBanner: { backgroundColor: '#4A2D3B', marginHorizontal: 15, padding: 8, borderRadius: 10 },
});
