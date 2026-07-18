import { useState } from 'react'
import { Form, Input, Modal, Select, message } from 'antd'
import { personaMarketApi } from '@/api/personaMarket'
import type { Persona } from '@/api/personas'

const { TextArea } = Input

const POPULAR_TAGS = [
  '情感陪伴', '创意写作', '学习导师', '职场参谋',
  '游戏娱乐', '生活助手', '心理咨询', '技术专家',
  '幽默搞笑', '哲学思辨',
]

interface Props {
  persona: Persona
  open: boolean
  onClose: () => void
  onPublished: () => void
}

export default function PublishPersonaModal({ persona, open, onClose, onPublished }: Props) {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)

  const handleOk = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      await personaMarketApi.publishPersona(persona.id, values)
      message.success('已发布到角色市场！')
      onPublished()
      onClose()
    } catch (e: any) {
      if (e?.errorFields) return // form validation
      message.error(e?.message || '发布失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={loading}
      okText="发布"
      cancelText="取消"
      title={`发布角色：${persona.name}`}
      width={520}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          market_name: persona.name,
          market_description: '',
          tags: [],
          icon: '🤖',
        }}
      >
        <Form.Item
          name="market_name"
          label="市场名称"
          rules={[{ required: true, message: '请输入' }, { max: 64 }]}
        >
          <Input placeholder="在市场中显示的名称" />
        </Form.Item>

        <Form.Item
          name="market_description"
          label="描述"
          rules={[{ required: true, message: '请输入描述' }, { max: 500 }]}
        >
          <TextArea rows={3} placeholder="介绍一下这个角色的特点，让其他人了解为什么值得导入" />
        </Form.Item>

        <Form.Item name="tags" label="标签（可选 1-5 个）">
          <Select
            mode="multiple"
            placeholder="选择标签，帮助别人找到你的角色"
            options={POPULAR_TAGS.map((t) => ({ label: t, value: t }))}
            maxCount={5}
          />
        </Form.Item>

        <Form.Item name="icon" label="图标">
          <Select
            options={[
              '🤖', '🧠', '💡', '🎯', '💪', '🎨', '📚', '🔬',
              '💼', '🎮', '❤️', '🌟', '🔥', '🌈', '🦊', '🐱',
            ].map((e) => ({ label: e, value: e }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
