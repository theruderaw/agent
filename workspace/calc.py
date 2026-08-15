#!/usr/bin/env python3

def main():
    total = 0
    while True:
        user_input = input("Enter a number: ").strip()
        if user_input.lower() == 'q':
            print(f"Sum: {total:.3f}")
            break
        try:
            num = float(user_input)
            total += num
        except ValueError:
            print("Invalid number. Please enter a valid number or q.")

if __name__ == '__main__':
    main()