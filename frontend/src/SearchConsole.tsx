import {
  AppstoreOutlined,
  CheckCircleOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  LoginOutlined,
  LogoutOutlined,
  ReloadOutlined,
  SearchOutlined,
  TagsOutlined,
  UserAddOutlined,
  UserOutlined
} from '@ant-design/icons';
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Empty,
  Flex,
  Form,
  Input,
  Layout,
  List,
  Menu,
  Pagination,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message
} from 'antd';
import type { MenuProps, TableColumnsType } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  apiGet,
  apiPost,
  type HistoryRow,
  type SearchHit,
  type SearchResponse,
  type TopicResponse
} from './api';

const { Header, Sider, Content } = Layout;
const { Text, Title, Paragraph } = Typography;

type User = { id: number; username: string; interests: string } | null;
type AuthResponse = { ok: boolean; message: string; user?: Exclude<User, null> };
type PageKey = 'search' | 'topics' | 'documents' | 'history' | 'account';
type SearchPreset = Partial<Record<'q' | 'site' | 'filetype' | 'mode' | 'section' | 'category', string>>;
type SearchFormValues = Record<string, string | undefined>;
type LoginFormValues = { username: string; password: string };
type RegisterFormValues = LoginFormValues & { confirm: string; interests?: string };
type ProfileFormValues = { interests?: string };

const DEFAULT_PAGE_SIZE = 10;
const PAGE_SIZE_OPTIONS = [10, 20, 50];
const DOCUMENT_TYPES = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'html'];

function clampPageForTotal(page: number, size: number, total: number) {
  const maxPage = Math.max(Math.ceil(total / Math.max(size, 1)), 1);
  return Math.min(Math.max(page, 1), maxPage);
}

const menuItems: MenuProps['items'] = [
  { key: 'search', icon: <SearchOutlined />, label: '搜索' },
  { key: 'topics', icon: <AppstoreOutlined />, label: '主题' },
  { key: 'documents', icon: <FileSearchOutlined />, label: '文档' },
  { key: 'history', icon: <HistoryOutlined />, label: '历史' },
  { key: 'account', icon: <UserOutlined />, label: '账号' }
];

const facetTitle: Record<string, string> = {
  domain: '站点',
  filetype: '类型',
  category: '主题'
};

const filterTitle: Record<string, string> = {
  site: '站内',
  filetype: '类型',
  category: '主题'
};

function stripHtml(value: string) {
  return value.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function externalUrl(value: string) {
  if (/^https?:\/\//i.test(value)) return value;
  return `https://${value.replace(/^\/+/, '')}`;
}

function sitePrefixFromDomain(domain: string) {
  const cleanDomain = domain.replace(/^https?:\/\//i, '').replace(/\/.*$/, '');
  const scheme = cleanDomain === '12club.nankai.edu.cn' ? 'http' : 'https';
  return `${scheme}://${cleanDomain}/`;
}

function formatCount(value: number | undefined | null) {
  return Number(value || 0).toLocaleString('zh-CN');
}

export function SearchConsole() {
  const [page, setPage] = useState<PageKey>('search');
  const [user, setUser] = useState<User>(null);
  const [searchPreset, setSearchPreset] = useState<SearchPreset | null>(null);

  const refreshUser = useCallback(async () => {
    const me = await apiGet<{ user: User }>('/api/me');
    setUser(me.user);
  }, []);

  useEffect(() => {
    refreshUser().catch((error) => message.error(`初始化失败：${error.message}`));
  }, [refreshUser]);

  const openPreset = useCallback((preset: SearchPreset) => {
    setSearchPreset(preset);
    setPage('search');
  }, []);

  return (
    <Layout className="shell">
      <Sider width={220} className="sidebar">
        <div className="logoBlock">
          <div className="logoMark">NK</div>
          <div>
            <Text strong>NKU Search</Text>
            <div className="subtle">南开资源搜索</div>
          </div>
        </div>
        <Menu mode="inline" selectedKeys={[page]} items={menuItems} onClick={(item) => setPage(item.key as PageKey)} />
      </Sider>
      <Layout>
        <Header className="topHeader">
          <Text strong>南开资源搜索</Text>
          <Space>
            <UserOutlined />
            <Text>{user ? user.username : '游客'}</Text>
          </Space>
        </Header>
        <Content className="content">
          {page === 'search' && <SearchPage preset={searchPreset} />}
          {page === 'topics' && <TopicPage onOpenSearch={openPreset} />}
          {page === 'documents' && <DocumentPage />}
          {page === 'history' && <HistoryPage />}
          {page === 'account' && <AccountPage user={user} onChanged={refreshUser} />}
        </Content>
      </Layout>
    </Layout>
  );
}

function TopicPage({ onOpenSearch }: { onOpenSearch: (preset: SearchPreset) => void }) {
  const [topics, setTopics] = useState<TopicResponse | null>(null);

  useEffect(() => {
    apiGet<TopicResponse>('/api/topics').then(setTopics).catch(() => undefined);
  }, []);

  const sections = useMemo(() => [...(topics?.sections || [])].sort((a, b) => b.priority - a.priority), [topics]);

  if (!topics) return <Card loading />;

  return (
    <Space direction="vertical" size={16} className="full">
      <Title level={2}>主题</Title>
      <Row gutter={[16, 16]} className="topicDeck">
        {sections.map((section) => (
          <Col xs={24} sm={12} lg={8} xl={6} key={section.key}>
            <Card className="topicCard">
              <Space direction="vertical" className="full" size={12}>
                <Flex justify="space-between" align="center">
                  <Text strong>{section.label}</Text>
                  <Tag color={section.key === 'anime' ? 'magenta' : 'green'}>{section.category}</Tag>
                </Flex>
                <Paragraph ellipsis={{ rows: 2 }}>{section.description}</Paragraph>
                <Flex justify="space-between" align="center">
                  <Text type="secondary">已索引</Text>
                  <Text strong>{formatCount(section.indexed_count)}</Text>
                </Flex>
                <Button
                  type="primary"
                  block
                  onClick={() => onOpenSearch({ q: section.key === 'anime' ? '动漫' : '南开', category: section.category })}
                >
                  搜索该主题
                </Button>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
    </Space>
  );
}

function SearchPage({ preset }: { preset: SearchPreset | null }) {
  const [form] = Form.useForm();
  const initialized = useRef(false);
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [suggestions, setSuggestions] = useState<Array<{ value: string }>>([]);
  const [recommendations, setRecommendations] = useState<string[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const latestSearchValues = useRef<SearchFormValues>({});

  const watchedSite = Form.useWatch('site', form);
  const watchedFiletype = Form.useWatch('filetype', form);
  const watchedCategory = Form.useWatch('category', form);
  const activeValues = useMemo<SearchFormValues>(
    () => ({
      site: watchedSite || '',
      filetype: watchedFiletype || '',
      category: watchedCategory || ''
    }),
    [watchedCategory, watchedFiletype, watchedSite]
  );

  const loadRecommendations = useCallback(async () => {
    const data = await apiGet<{ suggestions: string[] }>('/api/suggest?q=');
    setRecommendations(data.suggestions);
    return data.suggestions;
  }, []);

  const runSearch = useCallback(async (values: SearchFormValues, nextPage = 1, nextPageSize = DEFAULT_PAGE_SIZE) => {
    setLoading(true);
    latestSearchValues.current = values;
    setCurrentPage(nextPage);
    setPageSize(nextPageSize);
    try {
      const params = new URLSearchParams();
      Object.entries(values).forEach(([key, value]) => {
        if (value) params.set(key, value);
      });
      params.set('page', String(nextPage));
      params.set('size', String(nextPageSize));
      const data = await apiGet<SearchResponse>(`/api/search?${params.toString()}`);
      setResponse(data);
      loadRecommendations().catch(() => undefined);
    } catch (error) {
      message.error(`搜索失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [loadRecommendations]);

  const submitSearch = useCallback((value?: string) => {
    const q = value ?? form.getFieldValue('q') ?? '';
    const values = { ...form.getFieldsValue(true), q };
    form.setFieldsValue({ q });
    runSearch(values, 1, pageSize);
  }, [form, pageSize, runSearch]);

  const fetchSuggest = async (value: string) => {
    if (!value.trim()) {
      setSuggestions(recommendations.map((item) => ({ value: item })));
      return;
    }
    const data = await apiGet<{ suggestions: string[] }>(`/api/suggest?q=${encodeURIComponent(value)}`);
    setSuggestions(data.suggestions.map((item) => ({ value: item })));
  };

  const activeFilters = useMemo(
    () => ['site', 'filetype', 'category']
      .map((key) => ({ key, label: filterTitle[key], value: activeValues[key] }))
      .filter((item): item is { key: string; label: string; value: string } => Boolean(item.value)),
    [activeValues]
  );

  const runWithFilterPatch = useCallback((patch: SearchFormValues) => {
    const next = { ...form.getFieldsValue(true), ...patch };
    form.setFieldsValue(next);
    runSearch(next, 1, pageSize);
  }, [form, pageSize, runSearch]);

  const clearOneFilter = useCallback((key: string) => {
    runWithFilterPatch({ [key]: '' });
  }, [runWithFilterPatch]);

  const clearAllFilters = useCallback(() => {
    runWithFilterPatch({ site: '', filetype: '', category: '', section: '' });
  }, [runWithFilterPatch]);

  const toggleFacetFilter = useCallback((facetName: string, key: string) => {
    const next = { ...form.getFieldsValue(true) };
    if (facetName === 'filetype') next.filetype = next.filetype === key ? '' : key;
    if (facetName === 'domain') {
      const site = sitePrefixFromDomain(key);
      next.site = next.site === site ? '' : site;
    }
    if (facetName === 'category') next.category = next.category === key ? '' : key;
    form.setFieldsValue(next);
    runSearch(next, 1, pageSize);
  }, [form, pageSize, runSearch]);

  useEffect(() => {
    loadRecommendations().catch(() => undefined);
  }, [loadRecommendations]);

  useEffect(() => {
    if (preset) {
      const values = { q: '南开', mode: '', filetype: '', site: '', category: '', section: '', ...preset };
      form.setFieldsValue(values);
      runSearch(values);
    }
  }, [form, preset, runSearch]);

  useEffect(() => {
    if (initialized.current || preset) return;
    initialized.current = true;
    const values = { q: '', mode: '', filetype: '', site: '', category: '', section: '' };
    form.setFieldsValue(values);
    runSearch(values);
  }, [form, preset, runSearch]);

  return (
    <Space direction="vertical" size={16} className="full">
      <Card className="searchHero">
        <Form form={form} layout="vertical" onFinish={(values) => runSearch(values, 1, pageSize)}>
          <Row gutter={[12, 8]} align="top">
            <Col xs={24} lg={20} xl={18}>
              <Form.Item name="q" label="搜索" className="searchBoxItem">
                <AutoComplete options={suggestions} onSearch={fetchSuggest} onSelect={(value) => submitSearch(value)}>
                  <Input.Search
                    size="large"
                    enterButton="搜索"
                    loading={loading}
                    onSearch={(value) => submitSearch(value)}
                    placeholder="输入关键词"
                  />
                </AutoComplete>
              </Form.Item>
              {recommendations.length > 0 && (
                <div className="recommendBar">
                  <Text type="secondary">推荐</Text>
                  <div className="recommendList">
                    {recommendations.slice(0, 8).map((item) => (
                      <Button key={item} size="small" htmlType="button" onClick={() => submitSearch(item)}>
                        {item}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
            </Col>
            <Col xs={24} sm={10} md={7} lg={4}>
              <Form.Item name="mode" label="模式" className="compactFormItem">
                <Select options={[
                  { value: '', label: '自动' },
                  { value: 'normal', label: '普通' },
                  { value: 'phrase', label: '短语' },
                  { value: 'wildcard', label: '通配' },
                  { value: 'regex', label: '正则' }
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="site" hidden><Input /></Form.Item>
          <Form.Item name="filetype" hidden><Input /></Form.Item>
          <Form.Item name="category" hidden><Input /></Form.Item>
          <Form.Item name="section" hidden><Input /></Form.Item>
        </Form>
      </Card>

      <Row gutter={16}>
        <Col xs={24} lg={5}>
          <Card
            title="筛选"
            extra={<Button size="small" icon={<ReloadOutlined />} disabled={!activeFilters.length} onClick={clearAllFilters}>重置</Button>}
          >
            <Text type="secondary">数量为当前搜索结果内命中数</Text>
            {!activeFilters.length && <Text type="secondary">未启用筛选</Text>}
            {activeFilters.length > 0 && (
              <div className="activeFilters">
                <Text strong>当前筛选</Text>
                <Space wrap size={[4, 6]}>
                  {activeFilters.map((item) => (
                    <Tag
                      key={item.key}
                      closable
                      onClose={(event) => {
                        event.preventDefault();
                        clearOneFilter(item.key);
                      }}
                    >
                      {item.label}: {item.value}
                    </Tag>
                  ))}
                </Space>
              </div>
            )}
            {(response?.diagnostics?.facets || []).filter((facet) => facet.name !== 'section').map((facet) => (
              <div key={facet.name} className="facetBlock">
                <Text strong>{facetTitle[facet.name] || facet.name}</Text>
                {Object.entries(facet.buckets).map(([key, value]) => {
                  const selected =
                    (facet.name === 'filetype' && activeValues.filetype === key) ||
                    (facet.name === 'domain' && activeValues.site === sitePrefixFromDomain(key)) ||
                    (facet.name === 'category' && activeValues.category === key);
                  return (
                    <Button
                      key={key}
                      type={selected ? 'primary' : 'link'}
                      className="facetButton"
                      onClick={() => toggleFacetFilter(facet.name, key)}
                    >
                      <span>{key}</span>
                      <span className="facetCount">{value}</span>
                    </Button>
                  );
                })}
              </div>
            ))}
          </Card>
        </Col>
        <Col xs={24} lg={19}>
          <Space direction="vertical" className="full" size={12}>
            <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
              <Text type="secondary">共 {response?.total ?? 0} 条结果</Text>
              <Pagination
                current={currentPage}
                pageSize={pageSize}
                total={response?.total || 0}
                showSizeChanger
                pageSizeOptions={PAGE_SIZE_OPTIONS}
                showQuickJumper
                onChange={(nextPage: number, nextPageSize: number) => runSearch(latestSearchValues.current, clampPageForTotal(nextPage, nextPageSize, response?.total || 0), nextPageSize)}
                showTotal={(total: number, range: [number, number]) => `${range[0]}-${range[1]} / ${total}`}
              />
            </Flex>
            <List
              loading={loading}
              dataSource={response?.results || []}
              locale={{ emptyText: <Empty description="暂无结果" /> }}
              renderItem={(hit) => <SearchResult hit={hit} />}
            />
            <Pagination
              className="resultPagination"
              current={currentPage}
              pageSize={pageSize}
              total={response?.total || 0}
              showSizeChanger
              pageSizeOptions={PAGE_SIZE_OPTIONS}
              showQuickJumper
              onChange={(nextPage: number, nextPageSize: number) => runSearch(latestSearchValues.current, clampPageForTotal(nextPage, nextPageSize, response?.total || 0), nextPageSize)}
              showTotal={(total: number, range: [number, number]) => `${range[0]}-${range[1]} / ${total}`}
            />
          </Space>
        </Col>
      </Row>
    </Space>
  );
}

function SearchResult({ hit }: { hit: SearchHit }) {
  return (
    <List.Item>
      <Card className="resultCard">
        <div className="resultMain">
          <a
            className="resultTitle"
            href={externalUrl(hit.url)}
            target="_blank"
            rel="noreferrer"
            onClick={() => apiPost('/api/click', { doc_id: hit.doc_id, url: hit.url, title: hit.title }).catch(() => undefined)}
          >
            {hit.title}
          </a>
          <div className="resultUrl">{hit.url}</div>
          <Paragraph ellipsis={{ rows: 2, expandable: true }}>{stripHtml(hit.snippet)}</Paragraph>
          <Space wrap>
            <Tag color="cyan">{hit.filetype.toUpperCase()}</Tag>
            <Tag color="green">{hit.category}</Tag>
            <Button size="small" href={`/snapshot/${hit.doc_id}`} target="_blank">快照</Button>
          </Space>
        </div>
      </Card>
    </List.Item>
  );
}

function DocumentPage() {
  const [type, setType] = useState('pdf');
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const load = useCallback(async (filetype: string, nextPage = 1, nextPageSize = DEFAULT_PAGE_SIZE) => {
    setLoading(true);
    setType(filetype);
    setCurrentPage(nextPage);
    setPageSize(nextPageSize);
    try {
      const params = new URLSearchParams({ filetype, page: String(nextPage), size: String(nextPageSize) });
      const result = await apiGet<SearchResponse>(`/api/search?${params.toString()}`);
      setData(result);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load('pdf').catch(() => undefined); }, [load]);
  return (
    <Space direction="vertical" className="full" size={16}>
      <Card>
        <Flex justify="space-between" align="center" wrap="wrap" gap={12}>
          <Title level={2}>文档</Title>
          <Text type="secondary">共 {data?.total ?? 0} 条</Text>
        </Flex>
        <Segmented value={type} onChange={(value) => load(String(value), 1, pageSize)} options={DOCUMENT_TYPES} />
      </Card>
      <Pagination
        current={currentPage}
        pageSize={pageSize}
        total={data?.total || 0}
        showSizeChanger
        pageSizeOptions={PAGE_SIZE_OPTIONS}
        showQuickJumper
        onChange={(nextPage: number, nextPageSize: number) => load(type, clampPageForTotal(nextPage, nextPageSize, data?.total || 0), nextPageSize)}
        showTotal={(total: number, range: [number, number]) => `${range[0]}-${range[1]} / ${total}`}
      />
      <List
        loading={loading}
        dataSource={data?.results || []}
        locale={{ emptyText: <Empty description="暂无文档" /> }}
        renderItem={(item) => <SearchResult hit={item} />}
      />
      <Pagination
        className="resultPagination"
        current={currentPage}
        pageSize={pageSize}
        total={data?.total || 0}
        showSizeChanger
        pageSizeOptions={PAGE_SIZE_OPTIONS}
        showQuickJumper
        onChange={(nextPage: number, nextPageSize: number) => load(type, clampPageForTotal(nextPage, nextPageSize, data?.total || 0), nextPageSize)}
        showTotal={(total: number, range: [number, number]) => `${range[0]}-${range[1]} / ${total}`}
      />
    </Space>
  );
}

function HistoryPage() {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const columns: TableColumnsType<HistoryRow> = [
    { title: '时间', dataIndex: 'created_at', width: 210 },
    { title: '查询', dataIndex: 'query' },
    { title: '模式', dataIndex: 'mode', width: 120 },
    { title: '站点', dataIndex: 'site' },
    { title: '类型', dataIndex: 'filetype', width: 100 },
    { title: '结果', dataIndex: 'result_count', width: 90 }
  ];
  const refresh = async () => setRows((await apiGet<{ rows: HistoryRow[] }>('/api/history?all_users=true')).rows);
  useEffect(() => { refresh().catch(() => undefined); }, []);
  return (
    <Card title="历史">
      <Button onClick={refresh} style={{ marginBottom: 12 }}>刷新</Button>
      <Table rowKey="id" columns={columns} dataSource={rows} />
    </Card>
  );
}

function AccountPage({ user, onChanged }: { user: User; onChanged: () => Promise<void> }) {
  const [loginForm] = Form.useForm<LoginFormValues>();
  const [registerForm] = Form.useForm<RegisterFormValues>();
  const [profileForm] = Form.useForm<ProfileFormValues>();
  const [activeTab, setActiveTab] = useState('login');
  const [submitting, setSubmitting] = useState(false);
  const interestTags = useMemo(
    () => (user?.interests || '').split(/\s+/).map((item) => item.trim()).filter(Boolean),
    [user?.interests]
  );

  useEffect(() => {
    profileForm.setFieldsValue({ interests: user?.interests || '' });
  }, [profileForm, user?.interests]);

  const runAccountAction = async (action: () => Promise<void>) => {
    setSubmitting(true);
    try {
      await action();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const login = async (values: LoginFormValues) => {
    await runAccountAction(async () => {
      const response = await apiPost<AuthResponse>('/api/login', values);
      if (!response.ok) throw new Error(response.message || '登录失败');
      await onChanged();
      loginForm.resetFields(['password']);
      message.success(response.message || '已登录');
    });
  };

  const register = async (values: RegisterFormValues) => {
    await runAccountAction(async () => {
      const response = await apiPost<AuthResponse>('/api/register', {
        username: values.username,
        password: values.password,
        interests: values.interests || ''
      });
      if (!response.ok) throw new Error(response.message || '注册失败');
      await onChanged();
      registerForm.resetFields();
      message.success(response.message || '已注册并登录');
    });
  };

  const logout = async () => {
    await runAccountAction(async () => {
      await apiPost('/api/logout');
      await onChanged();
      message.success('已退出');
    });
  };

  const saveProfile = async (values: ProfileFormValues) => {
    await runAccountAction(async () => {
      const response = await apiPost<AuthResponse>('/api/profile', { interests: values.interests || '' });
      if (!response.ok) throw new Error(response.message || '更新失败');
      await onChanged();
      message.success(response.message || '已更新兴趣词');
    });
  };

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={9}>
        <Card
          title="账号状态"
          extra={user ? <Tag color="green" icon={<CheckCircleOutlined />}>已登录</Tag> : <Tag>游客</Tag>}
          className="accountCard"
        >
          {user ? (
            <Space direction="vertical" size={16} className="full">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="用户名">{user.username}</Descriptions.Item>
                <Descriptions.Item label="用户 ID">{user.id}</Descriptions.Item>
              </Descriptions>
              <div>
                <Text type="secondary">兴趣词</Text>
                <div className="tagDeck">
                  {interestTags.length ? interestTags.map((tag) => <Tag key={tag} color="cyan">{tag}</Tag>) : <Tag>未设置</Tag>}
                </div>
              </div>
            </Space>
          ) : (
            <Alert type="info" showIcon message="当前为游客" description="登录后搜索历史、点击记录和兴趣词会用于个性化排序。" />
          )}
          <Divider />
          <Button danger icon={<LogoutOutlined />} disabled={!user} loading={submitting} onClick={logout}>
            退出登录
          </Button>
        </Card>
      </Col>
      <Col xs={24} lg={15}>
        {user ? (
          <Card title="个性化设置" className="accountCard">
            <Form form={profileForm} layout="vertical" onFinish={saveProfile}>
              <Form.Item
                name="interests"
                label="兴趣词"
                extra="多个词用空格分隔，例如：人工智能 信息检索 图书馆"
              >
                <Input.TextArea rows={4} maxLength={160} showCount placeholder="人工智能 信息检索 图书馆" />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<TagsOutlined />} loading={submitting}>
                保存兴趣词
              </Button>
            </Form>
          </Card>
        ) : (
          <Card className="accountCard">
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              items={[
              {
                key: 'login',
                label: '登录账号',
                children: (
                  <Form form={loginForm} layout="vertical" onFinish={login} requiredMark={false}>
                    <Form.Item
                      name="username"
                      label="用户名"
                      rules={[
                        { required: true, message: '请输入用户名' },
                        { min: 2, message: '用户名至少 2 个字符' }
                      ]}
                    >
                      <Input prefix={<UserOutlined />} autoComplete="username" />
                    </Form.Item>
                    <Form.Item
                      name="password"
                      label="密码"
                      rules={[
                        { required: true, message: '请输入密码' },
                        { min: 4, message: '密码至少 4 位' }
                      ]}
                    >
                      <Input.Password autoComplete="current-password" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" icon={<LoginOutlined />} loading={submitting}>
                      登录
                    </Button>
                  </Form>
                )
              },
              {
                key: 'register',
                label: '注册账号',
                children: (
                  <Form form={registerForm} layout="vertical" onFinish={register} requiredMark={false}>
                    <Form.Item
                      name="username"
                      label="用户名"
                      rules={[
                        { required: true, message: '请输入用户名' },
                        { min: 2, message: '用户名至少 2 个字符' }
                      ]}
                    >
                      <Input prefix={<UserOutlined />} autoComplete="username" />
                    </Form.Item>
                    <Form.Item
                      name="password"
                      label="密码"
                      rules={[
                        { required: true, message: '请输入密码' },
                        { min: 4, message: '密码至少 4 位' }
                      ]}
                    >
                      <Input.Password autoComplete="new-password" />
                    </Form.Item>
                    <Form.Item
                      name="confirm"
                      label="确认密码"
                      dependencies={['password']}
                      rules={[
                        { required: true, message: '请再次输入密码' },
                        ({ getFieldValue }) => ({
                          validator(_, value) {
                            if (!value || getFieldValue('password') === value) return Promise.resolve();
                            return Promise.reject(new Error('两次输入的密码不一致'));
                          }
                        })
                      ]}
                    >
                      <Input.Password autoComplete="new-password" />
                    </Form.Item>
                    <Form.Item
                      name="interests"
                      label="兴趣词"
                      extra="用于个性化排序和搜索联想，可注册后继续修改。"
                    >
                      <Input prefix={<TagsOutlined />} maxLength={160} placeholder="人工智能 信息检索 图书馆" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" icon={<UserAddOutlined />} loading={submitting}>
                      注册并登录
                    </Button>
                  </Form>
                )
              }
            ]}
            />
          </Card>
        )}
      </Col>
    </Row>
  );
}






