using UnityEngine;

public class EnemyFootstepReceiver : MonoBehaviour
{
    // 這個方法接收腳步聲事件，但內容不做任何事
    void OnFootstep(AnimationEvent evt)
    {
        // 空的 → 不做任何事情，但阻止錯誤
    }

    // 有些動畫也會呼叫落地事件
    void OnLand(AnimationEvent evt)
    {
        // 也是空的
    }
}
