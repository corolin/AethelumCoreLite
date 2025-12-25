"""
审计Agent (AuditAgent)

实现输入和输出安全审查的聚合Agent
"""

import json
import logging
import random
from typing import Dict, List, Any, Optional
from ...core.message import NeuralImpulse
from ...core.protobuf_utils import ProtoBufManager
from ...prompts.moral_audit_prompts import MoralAuditPrompts


class Violation:
    """违规信息结构"""

    def __init__(
        self,
        violation_type: str,
        severity: str,
        description: str,
        confidence: float = 0.8
    ):
        self.type = violation_type
        self.severity = severity
        self.description = description
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "confidence": self.confidence
        }


class AuditStatus:
    """审查状态结构"""

    def __init__(self):
        self.status = "pending"  # approved, rejected, pending
        self.reason = ""
        self.violations: List[Violation] = []
        self.confidence = 0.0
        self.processed_at = None

    def approve(self, reason: str = "") -> None:
        """批准消息"""
        self.status = "approved"
        self.reason = reason
        self.confidence = 1.0

    def reject(self, reason: str, violations: List[Violation]) -> None:
        """拒绝消息"""
        self.status = "rejected"
        self.reason = reason
        self.violations = violations
        self.confidence = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "violations": [v.to_dict() for v in self.violations],
            "confidence": self.confidence
        }


class AuditAgent:
    """
    审计Agent - 实现输入和输出安全审查的聚合Agent

    基于设计文档的AuditAgent示例，实现N:1聚合模式，
    同时处理输入和输出两个强制性关卡。
    """

    def __init__(self, agent_name: str = "AuditAgent", ai_client: Optional[Any] = None):
        """
        初始化审计Agent

        Args:
            agent_name: Agent名称
            ai_client: AI客户端实例（支持OpenAI或智谱AI客户端）
        """
        self.agent_name = agent_name
        self.logger = logging.getLogger(f"audit.{agent_name}")
        self.ai_client = ai_client

        if not self.ai_client:
            raise RuntimeError("AuditAgent必须配置AI客户端（OpenAI或智谱AI）")

        self.logger.info("AuditAgent初始化完成")

    def process_input_audit(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        处理输入审查

        Args:
            impulse: 神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        import time
        start_time = time.time()
        self.logger.debug(f"[{time.strftime('%H:%M:%S.%f')[:-3]}] 开始输入审查: {impulse.session_id[:8]}...")

        try:
            # 获取用户输入内容
            user_content = impulse.get_text_content()

            # 执行AI内容审查
            audit_start = time.time()
            audit_status = self.audit_content(impulse)
            audit_end = time.time()
            self.logger.debug(f"AI内容审查完成，耗时: {(audit_end - audit_start):.3f}秒")

            # 将审查状态添加到脉冲元数据
            impulse.metadata['audit_input_status'] = audit_status.to_dict()
            impulse.metadata['audit_input_agent'] = self.agent_name

            # 更新源Agent信息
            impulse.update_source(f"{self.agent_name}_INPUT")

            if audit_status.status == "approved":
                # 审查通过，路由到审计后输入队列
                impulse.reroute_to("Q_AUDITED_INPUT")
                self.logger.debug(f"输入审查通过: {impulse.session_id[:8]}...")
                return impulse
            else:
                # 审查拒绝，生成拒绝回复
                violation_type = audit_status.violations[0].type  # 获取第一个违规类型

                # 生成拒绝回复
                rejection_response = self.generate_rejection_response(
                    violation_type=violation_type
                )

                # 更新脉冲内容为生成的拒绝回复
                impulse.set_text_content(rejection_response)

                # 将违规类型和审查结果存储在元数据中，供Q_RESPONSE_SINK使用
                impulse.metadata['audit_violation_type'] = violation_type
                impulse.metadata['audit_rejection_reason'] = audit_status.reason
                impulse.metadata['audit_failed_at_input'] = True

                # 如果是安全威胁，添加特殊标记
                if impulse.metadata.get('security_threat', False):
                    impulse.metadata['is_security_threat'] = True
                    threat_type = impulse.metadata.get('threat_type', 'unknown')

                # 路由到Q_RESPONSE_SINK进行最终响应处理
                impulse.reroute_to("Q_RESPONSE_SINK")
                return impulse

        except Exception as e:
            self.logger.error(f"输入审查失败: {e}")
            # 为异步框架创建错误脉冲发送到Q_ERROR_HANDLER
            error_impulse = impulse.create_error_response(
                error_message=str(e),
                error_source="AuditAgent.input_audit",
                original_session_id=impulse.session_id
            )
            error_impulse.reroute_to("Q_ERROR_HANDLER")
            return error_impulse


    def process_output_audit(self, impulse: NeuralImpulse, source_queue: str) -> NeuralImpulse:
        """
        处理输出审查

        Args:
            impulse: 神经脉冲
            source_queue: 源队列名称

        Returns:
            NeuralImpulse: 处理后的神经脉冲
        """
        try:
            # 获取输出内容
            user_content = impulse.get_text_content()

            # 执行AI内容审查
            audit_status = self.audit_content(impulse)

            # 将审查状态添加到脉冲元数据
            impulse.metadata['audit_output_status'] = audit_status.to_dict()
            impulse.metadata['audit_output_agent'] = self.agent_name

            # 更新源Agent信息
            impulse.update_source(f"{self.agent_name}_OUTPUT")

            if audit_status.status == "approved":
                # 审查通过，路由到响应发送器
                impulse.reroute_to("Q_RESPONSE_SINK")
            else:
                # 审查拒绝，生成拒绝回复
                if audit_status.violations:
                    violation_type = audit_status.violations[0].type  # 获取第一个违规类型
                else:
                    violation_type = "SecurityViolation"

                # 生成拒绝回复
                rejection_response = self.generate_rejection_response(
                    violation_type=violation_type
                )

                # 更新脉冲内容为生成的拒绝回复
                impulse.set_text_content(rejection_response)

                # 将违规类型和审查结果存储在元数据中，供Q_RESPONSE_SINK使用
                impulse.metadata['audit_violation_type'] = violation_type
                impulse.metadata['audit_rejection_reason'] = audit_status.reason
                impulse.metadata['audit_failed_at_output'] = True

                # 如果是安全威胁，添加特殊标记
                if impulse.metadata.get('security_threat', False):
                    impulse.metadata['is_security_threat'] = True
                    threat_type = impulse.metadata.get('threat_type', 'unknown')

                # 路由到Q_RESPONSE_SINK进行最终响应处理
                impulse.reroute_to("Q_RESPONSE_SINK")

        except Exception as e:
            self.logger.error(f"输出审查失败: {e}")
            # 为异步框架创建错误脉冲发送到Q_ERROR_HANDLER
            error_impulse = impulse.create_error_response(
                error_message=str(e),
                error_source="AuditAgent.output_audit",
                original_session_id=impulse.session_id
            )
            error_impulse.reroute_to("Q_ERROR_HANDLER")
            return error_impulse

        return impulse

    def generate_rejection_response(self, violation_type: str) -> str:
        """
        使用陪伴型AI模板和OpenAI客户端生成拒绝回复

        Args:
            violation_type: 违规类型

        Returns:
            str: 生成的拒绝回复
        """
        try:
            # 使用陪伴型AI模板作为系统提示词
            companion_prompt = MoralAuditPrompts.get_companion_prompt(violation_type)

            # 构建拒绝回复生成消息
            messages = [
                {"role": "system", "content": companion_prompt},
                {"role": "user", "content": f"Type: {violation_type}\n请根据模板生成拒绝回复。"}
            ]

            # 调用AI客户端生成拒绝回复
            response = self.ai_client.chat_completion(
                messages=messages,
                model=getattr(self.ai_client.config, 'audit_model', 'glm-4.5-flash'),
                temperature=0.7,  # 拒绝回复可以使用稍高的温度来产生更多样化的回复
                max_tokens=200
            )

            if "error" in response:
                self.logger.error(f"生成拒绝回复失败: {response['error']}")
                # 如果AI生成失败，使用简单的默认回复
                return f"抱歉，我无法处理包含{violation_type}类型的内容。让我们聊一些其他的话题吧。"

            # 解析生成的拒绝回复
            generated_response = response["choices"][0]["message"]["content"].strip()

            self.logger.debug(f"成功生成AI拒绝回复，类型: {violation_type}")
            return generated_response

        except Exception as e:
            self.logger.error(f"生成拒绝回复异常: {e}")
            # 兜底回复
            return f"抱歉，出于安全考虑，我无法处理此类请求。我们可以聊一些其他话题。"

    def audit_content(self, impulse: NeuralImpulse) -> AuditStatus:
        """
        使用OpenAI客户端进行内容审查

        Args:
            impulse: 神经脉冲

        Returns:
            AuditStatus: 审查结果
        """
        import time
        import json
        # 获取用户输入内容
        user_content = impulse.get_text_content()

        # 获取审计参数
        from ...prompts.moral_audit_prompts import MoralAuditPrompts
        system_prompt = MoralAuditPrompts.get_audit_prompt()

        # 构建审查消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        # 调用AI客户端的chat_completion方法
        audit_max_tokens = getattr(self.ai_client.config, 'audit_max_tokens', 1000)  # 增加默认token限制
        response = self.ai_client.chat_completion(
            messages=messages,
            model=getattr(self.ai_client.config, 'audit_model', 'glm-4.5-flash'),
            temperature=getattr(self.ai_client.config, 'audit_temperature', 0.0),
            max_tokens=audit_max_tokens
        )

        if "error" in response:
            raise RuntimeError(f"AI审查失败: {response['error']}")

        # 解析响应内容
        content = response["choices"][0]["message"]["content"]
        self.logger.debug(f"收到审查结果: {content}")

        # 清理markdown代码块（很多AI模型会在JSON前后添加```json标记）
        cleaned_content = content.strip()
        if cleaned_content.startswith('```json'):
            cleaned_content = cleaned_content[7:]  # 移除 ```json
        if cleaned_content.startswith('```'):
            cleaned_content = cleaned_content[3:]   # 移除 ```
        if cleaned_content.endswith('```'):
            cleaned_content = cleaned_content[:-3]   # 移除 ```
        cleaned_content = cleaned_content.strip()

        # 尝试解析JSON响应
        try:
            audit_response = json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            # 如果不是JSON，包装为字典
            self.logger.warning(f"JSON解析失败: {e}，使用原始内容作为响应")
            audit_response = {"content": cleaned_content}

        # 验证响应格式（只对有效JSON格式进行验证）
        from ...prompts.moral_audit_prompts import MoralAuditPrompts

        # 获取caesar_shift和nonce用于验证
        audit_parameters = impulse.metadata.get('audit_parameters', {})
        caesar_shift = audit_parameters.get('caesar_shift', 3)
        expected_nonce = audit_parameters.get('nonce', 'default_nonce_16')

        validation_result = MoralAuditPrompts.validate_audit_response(
            json.dumps(audit_response, ensure_ascii=False)
        )

        if not validation_result['valid']:
            # 检查是否是安全威胁
            if validation_result.get('security_threat', False):
                # 安全威胁：立即拒绝并记录威胁类型
                threat_type = validation_result.get('threat_type', 'unknown')
                error_msg = validation_result.get('error', 'Unknown security threat')
                self.logger.error(f"🚨 安全威胁检测到: {threat_type} - {error_msg}")

                # 创建审查状态 - 立即拒绝
                audit_status = AuditStatus()
                audit_status.reject(
                    reason=f"安全威胁检测: {threat_type} - {error_msg}",
                    violations=[
                        Violation(
                            violation_type=threat_type,
                            severity="critical",
                            description=f"检测到提示词注入攻击: {threat_type}",
                            confidence=1.0
                        )
                    ]
                )

                # 添加安全威胁信息到脉冲元数据
                impulse.metadata['security_threat'] = True
                impulse.metadata['threat_type'] = threat_type
                impulse.metadata['security_error'] = error_msg

                # 直接返回安全威胁审查状态
                return audit_status
            else:
                # 普通验证错误
                raise RuntimeError(f"AI响应验证失败: {validation_result.get('error')}")

        # 创建审查状态
        audit_status = AuditStatus()

        # 验证通过，按正常逻辑处理
        if validation_result['status'] == 'DIRTY':
            # 审查拒绝
            violation_type = validation_result['type']
            audit_status.reject(
                reason=f"AI审查发现违规类型: {violation_type}",
                violations=[
                    Violation(
                        violation_type=violation_type,
                        severity="high",
                        description=f"AI审查识别的{violation_type}类型违规",
                        confidence=1.0
                    )
                ]
            )
        else:
            # 审查通过
            audit_status.approve("AI审查通过")

        # 存储AI审查结果
        impulse.metadata['ai_audit_response'] = response
        impulse.metadata['ai_audit_content'] = audit_response
        impulse.metadata['ai_audit_validation'] = validation_result

        return audit_status
    
    def get_agent_info(self) -> Dict[str, Any]:
        """获取Agent信息"""
        return {
            "agent_name": self.agent_name,
            "agent_type": "AuditAgent",
            "capabilities": [
                "input_content_audit",
                "output_content_audit",
                "ai_client_integration",
                "moral_audit_ai_v2_prompts",
                "ai_powered_audit",
                "security_filtering",
                "protobuf_support",
                "dual_randomness_validation",
                "violation_response_generation"
            ],
            "features": {
                "moral_audit_ai_v2": True,
                "dual_randomness_validation": True,
                "system_prompt_injection": True,
                "protobuf_content": "mandatory",
                "ai_client_required": True,
                "no_local_fallback": True,
                "crash_on_missing_ai_client": True,
                "protobuf_compilation_required": True
            }
        }