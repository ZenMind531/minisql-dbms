CREATE TABLE student(id INT, name VARCHAR(32), age INT);
INSERT INTO student VALUES (1, 'Alice', 20);
SELECT name FROM student WHERE age > 18 AND id != 3;
DELETE FROM student WHERE id = 1;
