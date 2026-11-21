import type { Experiment, Paper, Project, Protocol, ResearchReport, RiskItem } from '../types'

export const initialProjects: Project[] = [
  {
    id: 'project-gnn', code: 'RL-024', name: '图神经网络分子性质预测',
    description: '复现 GIN 在 MoleculeNet 上的分子性质预测能力，验证不同聚合函数的影响。',
    status: '复现中', progress: 72, paperCount: 8, experimentCount: 24, updated: '12 分钟前',
    nextTask: '完成 GIN 消融实验', tags: ['图神经网络', '分子预测'], accent: 'violet',
  },
  {
    id: 'project-nmt', code: 'RL-023', name: '低资源机器翻译适配',
    description: '探索参数高效微调方法在低资源语言翻译任务中的泛化表现。',
    status: '实验中', progress: 46, paperCount: 5, experimentCount: 18, updated: '1 小时前',
    nextTask: '对比 LoRA 与 Adapter', tags: ['NLP', '参数高效微调'], accent: 'cyan',
  },
  {
    id: 'project-diffusion', code: 'RL-021', name: '扩散模型图像修复',
    description: '验证条件扩散模型在破损图像修复任务中的指标与稳定性。',
    status: '待验证', progress: 88, paperCount: 12, experimentCount: 36, updated: '昨天',
    nextTask: '复核 FID 评估数据', tags: ['扩散模型', '图像修复'], accent: 'amber',
  },
  {
    id: 'project-protein', code: 'RL-019', name: '蛋白质结构表示学习',
    description: '对比自监督结构编码器在下游接触预测任务中的表示质量。',
    status: '已归档', progress: 100, paperCount: 9, experimentCount: 31, updated: '3 天前',
    nextTask: '复现材料已归档', tags: ['蛋白质', '表示学习'], accent: 'blue',
  },
]

export const papers: Paper[] = [
  {
    id: 'paper-gin', title: 'How Powerful are Graph Neural Networks?',
    authors: 'Keyulu Xu, Weihua Hu, Jure Leskovec, Stefanie Jegelka', venue: 'ICLR', year: 2019,
    status: '已解析', confidence: 96, readTime: '18 min', tags: ['GNN', 'Graph Isomorphism'],
    summary: '提出图同构网络（GIN），从 Weisfeiler-Lehman 图同构测试出发分析图神经网络的表达能力上限。',
    contribution: '证明基于求和聚合的读出结构可在特定条件下达到 WL 测试的判别能力，并给出可复现的网络结构。',
  },
  {
    id: 'paper-mpnn', title: 'Neural Message Passing for Quantum Chemistry',
    authors: 'Justin Gilmer, Samuel S. Schoenholz, Patrick F. Riley', venue: 'ICML', year: 2017,
    status: '已解析', confidence: 93, readTime: '24 min', tags: ['MPNN', 'Quantum Chemistry'],
    summary: '将多种分子图神经网络统一为消息传递框架，并在 QM9 量子化学基准上验证其预测能力。',
    contribution: '抽象出消息函数、更新函数与读出函数三阶段计算图，为分子性质预测提供通用实现框架。',
  },
  {
    id: 'paper-gcn', title: 'Semi-Supervised Classification with Graph Convolutional Networks',
    authors: 'Thomas N. Kipf, Max Welling', venue: 'ICLR', year: 2017,
    status: '待复核', confidence: 87, readTime: '16 min', tags: ['GCN', 'Semi-supervised'],
    summary: '通过谱图卷积的一阶近似构建高效图卷积网络，在半监督节点分类任务上取得有效表现。',
    contribution: '提出重归一化传播规则，将图结构信息与节点特征编码结合，显著降低图卷积计算成本。',
  },
  {
    id: 'paper-attention', title: 'Graph Attention Networks',
    authors: 'Petar Veličković, Guillem Cucurull, Arantxa Casanova', venue: 'ICLR', year: 2018,
    status: '解析中', confidence: 72, readTime: '21 min', tags: ['GAT', 'Attention'],
    summary: '引入自注意力机制为邻接节点分配不同权重，避免依赖预先确定的图拉普拉斯结构。',
    contribution: '多头注意力增强了邻域聚合的表达能力，并可归纳泛化至训练期间不可见的图结构。',
  },
]

export const protocols: Protocol[] = [
  {
    id: 'protocol-gin', name: 'GIN 分子性质预测复现方案', project: '图神经网络分子性质预测', version: 'v1.4', updated: '今天 14:32', readiness: 86,
    steps: [
      { id: 's1', title: '环境与依赖核验', detail: 'Python 3.10 · PyTorch 2.1 · PyG 2.5 · CUDA 12.1', duration: '10 min', completed: true },
      { id: 's2', title: '数据集准备', detail: 'MoleculeNet / ESOL，固定 scaffold split，随机种子 42', duration: '20 min', completed: true },
      { id: 's3', title: '模型参数对齐', detail: '隐藏维度 300，5 层消息传递，dropout 0.5，求和聚合', duration: '15 min', completed: true },
      { id: 's4', title: '训练与过程记录', detail: 'Adam 优化器，学习率 1e-3，batch size 32，训练 100 epochs', duration: '90 min', completed: false },
      { id: 's5', title: '指标对照与结论', detail: '以论文 RMSE 为基线，允许 ±3% 波动，保存置信区间', duration: '25 min', completed: false },
    ],
  },
  {
    id: 'protocol-lora', name: '低资源翻译 LoRA 适配方案', project: '低资源机器翻译适配', version: 'v0.8', updated: '昨天 18:20', readiness: 64,
    steps: [
      { id: 'l1', title: '基座模型核验', detail: 'mT5-base · SentencePiece · 最大序列长度 512', duration: '15 min', completed: true },
      { id: 'l2', title: '双语语料清洗', detail: '去重、长度过滤与语言识别，保留 120k 平行语料', duration: '40 min', completed: true },
      { id: 'l3', title: 'LoRA 参数配置', detail: 'rank 16，alpha 32，dropout 0.1，作用于注意力投影层', duration: '15 min', completed: false },
      { id: 'l4', title: '训练与评估', detail: '以 sacreBLEU 和 COMET 为指标，对照全参数微调基线', duration: '120 min', completed: false },
    ],
  },
]

export const initialRisks: RiskItem[] = [
  { id: 'risk-1', level: 'high', title: '验证集存在重复样本', source: 'ESOL / scaffold split', detail: '检测到 14 组分子指纹高度相似，可能造成指标虚高。', status: '待处理' },
  { id: 'risk-2', level: 'medium', title: '随机种子记录不完整', source: 'Experiment #EXP-028', detail: '第 3、4 次运行缺少 NumPy 与 CUDA 随机种子配置。', status: '待处理' },
  { id: 'risk-3', level: 'medium', title: '评估库版本发生偏移', source: 'Environment / RDKit', detail: '当前 RDKit 2025.03 与论文环境的 2022.09 不一致。', status: '待处理' },
  { id: 'risk-4', level: 'low', title: '训练日志缺少磁盘快照', source: 'Experiment #EXP-024', detail: '建议将日志与模型权重纳入同一次制品归档。', status: '待处理' },
]

export const experiments: Experiment[] = [
  {
    id: 'exp-028', name: 'GIN · ESOL · Run 028', model: 'GIN-5L', dataset: 'ESOL', status: '运行中',
    epochs: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    trainLoss: [1.84, 1.25, .92, .72, .59, .49, .43, .38, .34, .31, .28],
    validationLoss: [1.91, 1.36, 1.06, .89, .78, .69, .65, .62, .61, .60, .60],
    baseline: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .58], reproduced: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .60],
    metric: 'Validation RMSE', metricValue: '0.603', delta: '+3.4% vs. paper',
  },
  {
    id: 'exp-024', name: 'GAT · ESOL · Run 024', model: 'GAT-4L', dataset: 'ESOL', status: '已完成',
    epochs: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    trainLoss: [1.76, 1.18, .88, .67, .54, .45, .39, .34, .30, .27, .24],
    validationLoss: [1.85, 1.32, 1.02, .84, .75, .67, .62, .59, .57, .56, .55],
    baseline: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .58], reproduced: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .55],
    metric: 'Validation RMSE', metricValue: '0.552', delta: '-4.8% vs. paper',
  },
  {
    id: 'exp-019', name: 'MPNN · QM9 · Run 019', model: 'MPNN-6L', dataset: 'QM9', status: '已暂停',
    epochs: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    trainLoss: [2.12, 1.54, 1.14, .91, .76, .65, .58, .51, .46, .42, .39],
    validationLoss: [2.20, 1.66, 1.27, 1.04, .91, .81, .75, .71, .69, .68, .67],
    baseline: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .70], reproduced: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .67],
    metric: 'Validation MAE', metricValue: '0.671', delta: '-4.1% vs. paper',
  },
]

export const reports: ResearchReport[] = [
  {
    id: 'report-gin', title: 'GIN 分子性质预测复现报告', type: '复现报告', updated: '今天 15:40', status: '草稿',
    abstract: '基于 MoleculeNet ESOL 数据集，对 GIN 的分子水溶性预测能力进行完整复现与偏差分析。',
    content: '## 1. 复现目标\n验证 GIN 在 ESOL 数据集上的 RMSE 指标，并分析数据划分与聚合函数对结果的影响。\n\n## 2. 环境与方法\n采用 PyTorch 2.1 与 PyG 2.5，隐藏维度 300，5 层消息传递，训练 100 epochs。\n\n## 3. 当前结果\n当前最优验证 RMSE 为 0.603，与论文参考值相差 +3.4%。需要进一步核验验证集中的重复样本。',
  },
  {
    id: 'report-nmt', title: '低资源翻译适配实验简报', type: '实验简报', updated: '昨天 19:12', status: '待审阅',
    abstract: '汇总 LoRA 与 Adapter 在低资源双语翻译任务上的初步对照实验。',
    content: '## 实验摘要\n在 120k 平行语料上比较 LoRA 与 Adapter 的样本效率。\n\n## 初步观察\nLoRA 在可训练参数量更低的情况下取得稳定 BLEU 表现，仍需补充 COMET 评估。',
  },
  {
    id: 'report-literature', title: '图神经网络分子建模文献综述', type: '文献综述', updated: '11 月 16 日', status: '已完成',
    abstract: '梳理消息传递、图同构与图注意力方法在分子性质预测中的技术演进。',
    content: '## 研究脉络\n从 MPNN 的统一消息传递框架，到 GIN 的表达能力分析与 GAT 的自适应邻域聚合。\n\n## 复现启示\n统一数据划分、环境版本和评估口径，是跨论文结果比较的必要条件。',
  },
]

export const taskGroups = [
  { label: '论文结构化理解', value: 100, detail: '8 / 8 篇', color: 'violet' as const },
  { label: '实验方案构建', value: 80, detail: '4 / 5 项', color: 'cyan' as const },
  { label: '核心实验复现', value: 68, detail: '17 / 25 组', color: 'violet' as const },
  { label: '结果审计与报告', value: 45, detail: '5 / 11 项', color: 'amber' as const },
]

export const agents = [
  { name: 'Paper Reader', task: '解析 Graph Attention Networks', state: '运行中', progress: 72 },
  { name: 'Protocol Agent', task: '等待核心实验完成', state: '待命', progress: 0 },
  { name: 'Data Inspector', task: '扫描 ESOL 数据分布', state: '运行中', progress: 46 },
]
