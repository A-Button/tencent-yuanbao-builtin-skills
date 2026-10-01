"""图书推荐共享模块：书库、错误信封与工具函数。"""

CATALOG = [
    {"id": "1", "title": "三体", "author": "刘慈欣",
     "description": "地球文明与三体文明的首次接触，一场跨越光年的宇宙社会学实验，中国科幻文学的里程碑。",
     "rating": 4.8, "category": "科幻"},
    {"id": "2", "title": "活着", "author": "余华",
     "description": "讲述一个人一生的故事，展现了中国社会变迁中普通人的苦难与坚韧，读来令人泪目。",
     "rating": 4.7, "category": "文学"},
    {"id": "3", "title": "百年孤独", "author": "加西亚·马尔克斯",
     "description": "布恩迪亚家族七代人的传奇故事，魔幻现实主义的巅峰之作，拉美文学的璀璨明珠。",
     "rating": 4.6, "category": "文学"},
    {"id": "4", "title": "1984", "author": "乔治·奥威尔",
     "description": "反乌托邦文学经典，描绘了一个极权主义社会对思想与自由的彻底剥夺，警世之作。",
     "rating": 4.6, "category": "文学"},
    {"id": "5", "title": "人类简史", "author": "尤瓦尔·赫拉利",
     "description": "从认知革命到科学革命，一部宏大的人类历史叙事，颠覆你对人类文明的认知。",
     "rating": 4.5, "category": "历史"},
    {"id": "6", "title": "小王子", "author": "圣埃克苏佩里",
     "description": "一个来自小行星的王子在地球上的奇遇，写给成年人的童话，关于爱与责任。",
     "rating": 4.7, "category": "文学"},
    {"id": "7", "title": "围城", "author": "钱钟书",
     "description": "中国现代文学经典，以幽默犀利的笔触描绘知识分子的婚姻困境与人生百态。",
     "rating": 4.6, "category": "文学"},
    {"id": "8", "title": "月亮与六便士", "author": "毛姆",
     "description": "一个证券经纪人抛弃一切追寻艺术梦想的故事，理想与现实之间的残酷抉择。",
     "rating": 4.4, "category": "文学"},
    {"id": "9", "title": "万历十五年", "author": "黄仁宇",
     "description": "以1587年为切口，剖析明朝衰落的结构性原因，大历史观的开山之作。",
     "rating": 4.5, "category": "历史"},
    {"id": "10", "title": "银河帝国：基地", "author": "艾萨克·阿西莫夫",
     "description": "心理史学预言银河帝国将灭亡，一位科学家试图缩短三万年的黑暗时代。",
     "rating": 4.5, "category": "科幻"},
    {"id": "11", "title": "杀死一只知更鸟", "author": "哈珀·李",
     "description": "关于种族歧视与正义的经典之作，透过一个女孩纯真的视角讲述勇气与良知。",
     "rating": 4.5, "category": "文学"},
    {"id": "12", "title": "红楼梦", "author": "曹雪芹",
     "description": "中国古典文学巅峰，以贾宝玉与林黛玉的爱情悲剧为主线，写尽人间百态。",
     "rating": 4.9, "category": "文学"},
    {"id": "13", "title": "时间简史", "author": "史蒂芬·霍金",
     "description": "关于宇宙起源与本质的科普经典，用通俗语言讲述时间、黑洞与宇宙的奥秘。",
     "rating": 4.3, "category": "科普"},
    {"id": "14", "title": "平凡的世界", "author": "路遥",
     "description": "以中国七十到八十年代为背景，展现普通人在大时代变迁中的奋斗与坚守。",
     "rating": 4.6, "category": "文学"},
    {"id": "15", "title": "思考，快与慢", "author": "丹尼尔·卡尼曼",
     "description": "诺贝尔经济学奖得主揭示人类认知的两套系统，帮你理解日常决策的偏误。",
     "rating": 4.3, "category": "心理学"},
    {"id": "16", "title": "局外人", "author": "阿尔贝·加缪",
     "description": "存在主义文学代表作，一个对世界漠然的男人，在荒诞中寻找生命的意义。",
     "rating": 4.4, "category": "文学"},
    {"id": "17", "title": "苏菲的世界", "author": "乔斯坦·贾德",
     "description": "以小说的形式讲述西方哲学史，深入浅出的哲学启蒙读物，引人入胜。",
     "rating": 4.3, "category": "哲学"},
    {"id": "18", "title": "明朝那些事儿", "author": "当年明月",
     "description": "用幽默通俗的语言讲述明朝三百年兴衰，让历史变得生动有趣。",
     "rating": 4.5, "category": "历史"},
    {"id": "19", "title": "白夜行", "author": "东野圭吾",
     "description": "两个孩子在绝望中互相守护，命运的齿轮将他们推向深渊，东野圭吾巅峰之作。",
     "rating": 4.5, "category": "推理"},
    {"id": "20", "title": "你当像鸟飞往你的山", "author": "塔拉·韦斯特弗",
     "description": "一个从未上过学的女孩最终获得剑桥博士学位的真实故事，教育的力量令人震撼。",
     "rating": 4.4, "category": "传记"},
]

CATEGORIES = sorted(set(b["category"] for b in CATALOG))


class ActionError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


def make_result(operation: str, books: list, **extra) -> dict:
    """构建标准响应：书籍列表 + 计数 + 额外字段。"""
    result = {"operation": operation, "books": books, "count": len(books)}
    result.update(extra)
    return result


def error_envelope(code: str, message: str, retryable: bool = True) -> dict:
    return {"phase": "error", "code": code, "message": message, "retryable": retryable}