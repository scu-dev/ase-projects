#include <cstdlib>
#include <iostream>
#include <memory>

/*================ 行为策略 =================*/
class BehaviorStrategy {
public:
    virtual ~BehaviorStrategy() = default;
    virtual void perform() const = 0;
};

class JumpBehavior : public BehaviorStrategy {
public:
    void perform() const override { std::cout << "---行为：蹦蹦跳跳" << std::endl; }
};

class SpinBehavior : public BehaviorStrategy {
public:
    void perform() const override { std::cout << "---行为：转圈圈" << std::endl; }
};

class FlyBehavior : public BehaviorStrategy {
public:
    void perform() const override { std::cout << "---行为：飞起来了" << std::endl; }
};

/*================ 叫声策略 =================*/
class SoundStrategy {
public:
    virtual ~SoundStrategy() = default;
    virtual void makeSound() const = 0;
};

class QuackSound : public SoundStrategy {
public:
    void makeSound() const override { std::cout << "---叫声：嘎嘎嘎好开心" << std::endl; }
};

class MeowSound : public SoundStrategy {
public:
    void makeSound() const override { std::cout << "---叫声：喵喵喵好漂亮" << std::endl; }
};

class BarkSound : public SoundStrategy {
public:
    void makeSound() const override { std::cout << "---叫声：汪汪汪太酷了" << std::endl; }
};

/* ================= 小鸭 ================= */
class Duck {
private:
    std::unique_ptr<BehaviorStrategy> behavior;
    std::unique_ptr<SoundStrategy> sound;

public:
    void setBehavior(std::unique_ptr<BehaviorStrategy> b) { behavior = std::move(b); }
    void setSound(std::unique_ptr<SoundStrategy> s) { sound = std::move(s); }

    void act() const {
        behavior->perform();
        sound->makeSound();
    }
};

int main() {
#ifdef _WIN32
    system("chcp 65001 > nul");
#endif
    Duck duck;

    std::cout << "1. 小鸭抢到红包" << std::endl;
    duck.setBehavior(std::make_unique<JumpBehavior>());
    duck.setSound(std::make_unique<QuackSound>());
    duck.act();

    std::cout << "2. 小鸭拿着红包买到新衣服" << std::endl;
    duck.setBehavior(std::make_unique<SpinBehavior>());
    duck.setSound(std::make_unique<MeowSound>());
    duck.act();

    std::cout << "3. 小鸭穿上新衣服" << std::endl;
    duck.setBehavior(std::make_unique<FlyBehavior>());
    duck.setSound(std::make_unique<BarkSound>());
    duck.act();

    return 0;
}
