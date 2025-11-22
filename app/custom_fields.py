from wtforms.fields import DateField
from wtforms.widgets import TextInput
from wtforms.validators import Optional
from datetime import date
import jdatetime

class JalaliDateField(DateField):
    def _value(self):
        try:
            if isinstance(self.data, str):
                # Try to parse the string
                d = datetime.strptime(self.data, "%Y-%m-%d").date()
                self.data = d
            jalali = JalaliDate.to_jalali(self.data)
            return f"{jalali.year:04}/{jalali.month:02}/{jalali.day:02}"
        except Exception:
            return ''

    def process_formdata(self, valuelist):
        if valuelist:
            try:
                jalali_str = valuelist[0].strip()
                parts = list(map(int, jalali_str.split('/')))
                gregorian = JalaliDate(parts[0], parts[1], parts[2]).to_gregorian()
                self.data = date(gregorian.year, gregorian.month, gregorian.day)
            except Exception as e:
                self.data = None
                raise ValueError('تاریخ نامعتبر است: {}'.format(str(e)))
