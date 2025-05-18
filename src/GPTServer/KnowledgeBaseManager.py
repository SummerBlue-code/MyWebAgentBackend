import uuid
import time
import logging
import chromadb
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from src.interface.MessageFormat import MessageFormat
from src.database.operations import DatabaseOperations
from src.database.base import Database
from src.models.GPTModel import GPTModel
from src.database.models import UserKnowledgeBase, KnowledgeBaseFile
from src.interface.ErrorCode import ErrorCode
from src.interface.GPTServerError import GPTServerError
from fastapi import UploadFile

logger = logging.getLogger(__name__)

class KnowledgeBaseManager:
    """知识库管理器"""
    
    def __init__(self, db_ops: DatabaseOperations, model: GPTModel):
        """初始化知识库管理器
        
        Args:
            db_ops (DatabaseOperations): 数据库操作实例
            model (GPTModel): GPT模型实例
        """
        self.db_ops = db_ops
        self.model = model
        self.knowledge_base = chromadb.PersistentClient(path="./db/chroma_demo")

    def create_knowledge_base(self, user_id: str, title: Optional[str] = None) -> str:
        """创建知识库
        
        Args:
            user_id (str): 用户ID
            title (Optional[str]): 知识库标题，如果为None则自动生成
            
        Returns:
            str: 知识库ID
            str: 知识库标题

        Raises:
            GPTServerError: 创建知识库失败时抛出
        """
        try:
            knowledge_base_id = str(uuid.uuid1())
            
            # 如果没有提供标题，使用默认标题
            if not title:
                title = "未命名的知识库"
            
            user_knowledge_base = UserKnowledgeBase(
                kb_id=knowledge_base_id,
                user_id=user_id,
                title=title,
                created_time=datetime.now()
            )
            
            success = self.db_ops.create_user_knowledge_base(user_knowledge_base)
            if not success:
                raise GPTServerError("创建知识库失败", ErrorCode.SERVER_INTERNAL_ERROR)
                
            logger.info(f"成功创建知识库 {knowledge_base_id} 给用户 {user_id}")
            return knowledge_base_id, title
            
        except Exception as e:
            logger.error(f"创建知识库失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"创建知识库失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR)

    def get_user_knowledge_bases(self, user_id: str) -> List[UserKnowledgeBase]:
        """获取用户的所有知识库
        
        Args:
            user_id (str): 用户ID
            
        Returns:
            List[UserKnowledgeBase]: 知识库列表
            
        Raises:
            GPTServerError: 获取知识库列表失败时抛出
        """
        try:
            knowledge_bases = self.db_ops.get_user_knowledge_bases(user_id)
            logger.info(f"成功获取用户 {user_id} 的知识库列表")
            return knowledge_bases
        except Exception as e:
            logger.error(f"获取用户知识库列表失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"获取用户知识库列表失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR)
    
    def update_knowledge_base_title(self, knowledge_base_id: str, title: str) -> None:
        """更新知识库标题
        
        Args:
            knowledge_base_id (str): 知识库ID
            title (str): 新标题
            
        Raises:
            GPTServerError: 更新标题失败时抛出
        """
        try:
            # 检查知识库是否存在
            knowledge_base = self.db_ops.get_knowledge_base(knowledge_base_id)
            if not knowledge_base:
                raise GPTServerError("知识库不存在", ErrorCode.SERVER_INTERNAL_ERROR)
            
            success = self.db_ops.update_knowledge_base_title(knowledge_base_id, title)
            if not success:
                raise GPTServerError("更新知识库标题失败", ErrorCode.SERVER_INTERNAL_ERROR)
                
            logger.info(f"成功更新知识库 {knowledge_base_id} 的标题为: {title}")
            
        except Exception as e:
            logger.error(f"更新知识库标题失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"更新知识库标题失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR)

    async def update_file_to_knowledge_base(self, knowledge_base_id: str, file: UploadFile) -> Dict[str, Any]:
        """上传文件到知识库
        
        Args:
            knowledge_base_id (str): 知识库ID
            file: 文件对象
            
        Returns:
            Dict[str, Any]: 上传结果
            
        Raises:
            GPTServerError: 上传文件失败时抛出
        """
        try:
            # 检查知识库是否存在
            knowledge_base = self.db_ops.get_knowledge_base(knowledge_base_id)
            if not knowledge_base:
                raise GPTServerError("知识库不存在", ErrorCode.SERVER_INTERNAL_ERROR)
            
            # 检查文件类型
            allowed_types = ['.txt', '.md', '.pdf', '.doc', '.docx']
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext not in allowed_types:
                raise GPTServerError(f"不支持的文件类型: {file_ext}", ErrorCode.INVALID_PARAMETER)
            
            # 生成文件ID
            file_id = str(uuid.uuid1())
            
            # 创建文件保存路径
            save_dir = os.path.join("uploads", knowledge_base_id)
            os.makedirs(save_dir, exist_ok=True)
            file_path = os.path.join(save_dir, f"{file_id}{file_ext}")
            
            # 保存文件
            file_content = await file.read()
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            # 生成文件摘要
            summary = self.model.generate_summary(
                file_content.decode('utf-8', errors='ignore')
            )
            
            # 创建文件记录
            file_message = KnowledgeBaseFile(
                file_id=file_id,
                knowledge_base_id=knowledge_base_id,
                file_name=file.filename,
                file_path=file_path,
                summary=summary,
                created_time=datetime.now()
            )
            
            # 保存文件记录
            success = self.db_ops.create_knowledge_base_file(file_message)
            if not success:
                # 如果保存记录失败，删除已上传的文件
                os.remove(file_path)
                raise GPTServerError("保存文件记录失败", ErrorCode.SERVER_INTERNAL_ERROR)
            
            # 处理文件内容
            docs = self.split_content(file_content.decode('utf-8', errors='ignore'))
            ids = self.docs_ids(docs)
            embeds = self.model.embed_texts(docs)
            
            # 添加到向量数据库
            knowledge_base_collection = self.knowledge_base.get_or_create_collection(
                name=knowledge_base_id
            )
            knowledge_base_collection.add(
                ids=ids,
                documents=docs,
                embeddings=embeds,
            )
            
            logger.info(f"成功将文件 {file.filename} 添加到知识库 {knowledge_base_id}")
            
            return {
                "file_id": file_id,
                "file_name": file.filename,
                "file_path": file_path,
                "summary": summary,
                "created_time": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"更新文件到知识库失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"更新文件到知识库失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR)
        finally:
            # 确保文件被关闭
            await file.close()

    def get_knowledge_base_files(self, knowledge_base_id: str) -> List[KnowledgeBaseFile]:
        """获取知识库的所有文件
        
        Args:
            knowledge_base_id (str): 知识库ID
            
        Returns:
            List[KnowledgeBaseFile]: 文件列表
            
        Raises:
            GPTServerError: 获取文件列表失败时抛出
        """
        try:
            # 检查知识库是否存在
            knowledge_base = self.db_ops.get_knowledge_base(knowledge_base_id)
            if not knowledge_base:
                raise GPTServerError("知识库不存在", ErrorCode.SERVER_INTERNAL_ERROR)
            
            files = self.db_ops.get_knowledge_base_files(knowledge_base_id)
            logger.info(f"成功获取知识库 {knowledge_base_id} 的文件列表")
            return files
        except Exception as e:
            logger.error(f"获取知识库文件列表失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"获取知识库文件列表失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR)

    def search_texts_in_knowledge_base(self, knowledge_base_id: str, question: str) -> Dict[str, Any]:
        """在知识库中搜索文本
        
        Args:
            knowledge_base_id (str): 知识库ID
            question (str): 搜索问题
            
        Returns:
            Dict[str, Any]: 搜索结果
            
        Raises:
            GPTServerError: 搜索失败时抛出
        """
        try:
            # 检查知识库是否存在
            knowledge_base = self.db_ops.get_knowledge_base(knowledge_base_id)
            if not knowledge_base:
                raise GPTServerError("知识库不存在", ErrorCode.SERVER_INTERNAL_ERROR)
            
            # 分割问题文本
            question_texts = self.split_content(question)
            
            # 生成问题文本的嵌入向量
            question_embeds = self.model.embed_texts(question_texts)
            
            # 获取知识库集合
            collection = self.knowledge_base.get_or_create_collection(name=knowledge_base_id)
            
            # 执行搜索
            results = collection.query(
                query_embeddings=question_embeds,
                query_texts=question_texts,
                n_results=3
            )
            
            texts = results["documents"][0]

            logger.info(f"在知识库 {knowledge_base_id} 中搜索问题: {question}")
            logger.info(f"搜索结果: {texts}")

            return texts
            
        except Exception as e:
            logger.error(f"搜索知识库失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"搜索知识库失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR)

    def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        """删除知识库
        
        Args:
            knowledge_base_id (str): 知识库ID
            
        Raises:
            GPTServerError: 删除失败时抛出
        """
        try:
            # 检查知识库是否存在
            knowledge_base = self.db_ops.get_knowledge_base(knowledge_base_id)
            if not knowledge_base:
                raise GPTServerError("知识库不存在", ErrorCode.SERVER_INTERNAL_ERROR)
            
            # 获取知识库的所有文件
            files = self.db_ops.get_knowledge_base_files(knowledge_base_id)
            
            # 如果存在文件，则删除文件
            if files:
                collection = self.knowledge_base.get_or_create_collection(name=knowledge_base_id)
                
                # 删除每个文件
                for file in files:
                    try:
                        # 从数据库中删除文件记录
                        self.db_ops.delete_knowledge_base_file(file.file_id)
                        
                        # 从向量数据库中删除文件向量
                        collection.delete(ids=[file.file_id])
                        
                        # 删除实际文件
                        save_dir = os.path.join("uploads", knowledge_base_id)
                        self.safe_delete_file(save_dir, file.file_id)
                        
                        logger.info(f"成功删除知识库文件 {file.file_id}")
                    except Exception as e:
                        logger.error(f"删除知识库文件 {file.file_id} 失败: {str(e)}", exc_info=True)
                        # 继续删除其他文件，不中断整个删除过程
            
                # 从向量数据库中删除集合
                self.knowledge_base.delete_collection(name=knowledge_base_id)
            
            # 从数据库中删除知识库记录
            success = self.db_ops.delete_knowledge_base(knowledge_base_id)
            if not success:
                raise GPTServerError("删除知识库记录失败", ErrorCode.SERVER_INTERNAL_ERROR)
            
            # 删除知识库目录
            save_dir = os.path.join("uploads", knowledge_base_id)
            if os.path.exists(save_dir):
                try:
                    os.rmdir(save_dir)
                except Exception as e:
                    logger.warning(f"删除知识库目录 {save_dir} 失败: {str(e)}")
                
            logger.info(f"成功删除知识库 {knowledge_base_id}")
            
        except Exception as e:
            logger.error(f"删除知识库失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"删除知识库失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR)

    def delete_knowledge_base_file(self, knowledge_base_id: str, file_id: str) -> None:
        """删除知识库文件
        
        Args:
            knowledge_base_id (str): 知识库ID
            file_id (str): 文件ID
            
        Raises:
            GPTServerError: 删除失败时抛出
        """
        try:
            # 检查文件是否存在
            file = self.db_ops.get_knowledge_base_file(file_id)
            if not file:
                raise GPTServerError("文件不存在", ErrorCode.SERVER_INTERNAL_ERROR)
            
            # 从数据库中删除文件记录
            success = self.db_ops.delete_knowledge_base_file(file_id)
            if not success:
                raise GPTServerError("删除文件记录失败", ErrorCode.SERVER_INTERNAL_ERROR)

            # 从向量数据库中删除文件向量
            collection = self.knowledge_base.get_or_create_collection(name=knowledge_base_id)
            collection.delete(ids=[file_id])

            # 删除上传的文件
            save_dir = os.path.join("uploads", knowledge_base_id)
            if os.path.exists(save_dir):
                self.safe_delete_file(save_dir, file_id)

            logger.info(f"成功删除知识库文件 {file_id}")
            
        except Exception as e:
            logger.error(f"删除知识库文件失败: {str(e)}", exc_info=True)
            raise GPTServerError(f"删除知识库文件失败: {str(e)}", ErrorCode.SERVER_INTERNAL_ERROR)

    @staticmethod
    def safe_delete_file(target_dir, filename):
        for entry in os.listdir(target_dir):
            entry_path = os.path.join(target_dir, entry)
            if os.path.isfile(entry_path):
                name_without_ext = os.path.splitext(entry)[0]
                if name_without_ext == filename:
                    os.remove(entry_path)
                    return

    @staticmethod
    def docs_ids(texts: List[str]) -> List[str]:
        """生成文档ID列表
        
        Args:
            texts (List[str]): 文本列表
            
        Returns:
            List[str]: 文档ID列表
        """
        return [str(uuid.uuid1()) for _ in texts]

    @staticmethod
    def split_content(content: str, max_length: int = 256) -> List[str]:
        """分割内容
        
        Args:
            content (str): 内容
            max_length (int): 最大长度
            
        Returns:
            List[str]: 分割后的内容列表
        """
        chunks = []
        for i in range(0, len(content), max_length):
            chunks.append(content[i:i + max_length])
        return chunks 