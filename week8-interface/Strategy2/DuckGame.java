package Strategy2;

/**
 * 小鸭行为与叫声
 */

public class DuckGame {
    /*================ 行为策略 =================*/
    interface BehaviorStrategy { void perform(); }

    static class JumpBehavior implements BehaviorStrategy {
        public void perform() { System.out.println("---行为：蹦蹦跳跳"); }
    }

    static class SpinBehavior implements BehaviorStrategy {
        public void perform() { System.out.println("---行为：转圈圈"); }
    }

    static class FlyBehavior implements BehaviorStrategy {
        public void perform() { System.out.println("---行为：飞起来了"); }
    }

    /*================ 叫声策略 =================*/
    interface SoundStrategy { void makeSound(); }

    static class QuackSound implements SoundStrategy {
        public void makeSound() { System.out.println("---叫声：嘎嘎嘎好开心"); }
    }

    static class MeowSound implements SoundStrategy {
        public void makeSound() { System.out.println("---叫声：喵喵喵好漂亮"); }
    }

    static class BarkSound implements SoundStrategy {
        public void makeSound() { System.out.println("---叫声：汪汪汪太酷了"); }
    }

    /* ================= 小鸭 ================= */
    static class Duck {
        private BehaviorStrategy behavior;
        private SoundStrategy sound;

        public void setBehavior(BehaviorStrategy b) { this.behavior = b; }
        public void setSound(SoundStrategy s) { this.sound = s; }

        public void act() {
            behavior.perform();
            sound.makeSound();
        }
    }

    public static void main(String[] args) {
        Duck duck = new Duck();

        System.out.println("1. 小鸭抢到红包");
        duck.setBehavior(new JumpBehavior());
        duck.setSound(new QuackSound());
        duck.act();

        System.out.println("2. 小鸭拿着红包买到新衣服");
        duck.setBehavior(new SpinBehavior());
        duck.setSound(new MeowSound());
        duck.act();

        System.out.println("3. 小鸭穿上新衣服");
        duck.setBehavior(new FlyBehavior());
        duck.setSound(new BarkSound());
        duck.act();
    }
}