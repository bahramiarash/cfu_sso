from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, SelectMultipleField, SubmitField
from wtforms.validators import DataRequired, Optional
from wtforms.fields import DateTimeField
from wtforms.fields import DateField
from wtforms.widgets import TextInput
from custom_fields import JalaliDateField

class TaskForm(FlaskForm):
    title = StringField('عنوان', validators=[DataRequired()])
    description = TextAreaField('شرح')
    assignee_ids = SelectMultipleField('کاربران مسئول', coerce=int)
    due_date = StringField('تاریخ سررسید', validators=[Optional()])
    start_date = StringField('تاریخ آغاز', validators=[Optional()])
    column_id = SelectField('ستون', coerce=int)
    submit = SubmitField('ثبت')

class TaskEditForm(FlaskForm):
    title = StringField('عنوان', validators=[DataRequired()])
    description = TextAreaField('شرح')
    start_date = StringField('تاریخ شروع', validators=[Optional()])
    due_date = StringField('تاریخ پایان', validators=[Optional()])
    column_id = SelectField('ستون', coerce=int, validators=[DataRequired()])
    submit = SubmitField('ویرایش وظیفه')

class ReportForm(FlaskForm):
    text = TextAreaField('گزارش', validators=[DataRequired()])
    submit = SubmitField('افزودن گزارش')
