/**
 * Membership form for creating new memberships.
 */
import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Button,
    Card,
    CardContent,
    TextField,
    Typography,
    Grid,
    MenuItem,
    Autocomplete,
    CircularProgress,
    InputAdornment
} from '@mui/material';
import { membershipsApi, MembershipCreate } from '@/api/memberships';
import { membersApi } from '@/api/members';
import { membershipPlansApi } from '@/api/membershipPlans';
import { addDays, addMonths, format } from 'date-fns';
import { useLanguage } from '@/i18n/LanguageContext';

const membershipSchema = z.object({
    member_id: z.string().min(1, 'Member is required'),
    plan_id: z.string().optional(),
    type: z.string().min(1, 'Membership name is required'),
    start_date: z.string().min(1, 'Start date is required'),
    end_date: z.string().min(1, 'End date is required'),
    price: z.number().min(0, 'Price must be positive'),
});

type MembershipFormData = z.infer<typeof membershipSchema>;

export const MembershipForm: React.FC = () => {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { t } = useLanguage();

    const { data: membersResponse, isLoading: membersLoading } = useQuery({
        queryKey: ['members-lookup'],
        queryFn: () => membersApi.getMembers({ limit: 100 }),
    });

    const { data: plansData, isLoading: plansLoading } = useQuery({
        queryKey: ['membership-plans'],
        queryFn: () => membershipPlansApi.getPlans(true),
    });
    const plans = plansData?.plans || [];

    const {
        control,
        handleSubmit,
        watch,
        setValue,
        formState: { errors },
    } = useForm<MembershipFormData>({
        resolver: zodResolver(membershipSchema),
        defaultValues: {
            member_id: '',
            plan_id: '',
            type: '',
            start_date: format(new Date(), 'yyyy-MM-dd'),
            end_date: format(addMonths(new Date(), 1), 'yyyy-MM-dd'),
            price: 0,
        },
    });

    const watchPlanId = watch('plan_id');
    const watchStartDate = watch('start_date');

    useEffect(() => {
        if (!watchPlanId) return;
        const plan = plans.find(p => p.id === watchPlanId);
        if (plan) {
            setValue('type', plan.name);
            setValue('price', Number(plan.price));
            const start = watchStartDate ? new Date(watchStartDate + 'T12:00:00') : new Date();
            let end = start;
            if (plan.duration_months) end = addMonths(end, plan.duration_months);
            if (plan.duration_days) end = addDays(end, plan.duration_days);
            setValue('end_date', format(end, 'yyyy-MM-dd'));
        }
    }, [watchPlanId, watchStartDate, plans, setValue]);

    const createMutation = useMutation({
        mutationFn: (data: MembershipCreate) => membershipsApi.createMembership(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['memberships'] });
            navigate('/memberships');
        },
    });

    const onSubmit = (data: MembershipFormData) => {
        const submitData: MembershipCreate = {
            member_id: data.member_id,
            plan_id: data.plan_id || undefined,
            type: data.type,
            start_date: data.start_date,
            end_date: data.end_date,
            price: data.price
        };
        createMutation.mutate(submitData);
    };

    if (membersLoading || plansLoading) {
        return (
            <Box display="flex" justifyContent="center" p={5}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <Box>
            <Typography variant="h4" gutterBottom>
                {t.memberships.newMembership}
            </Typography>

            <Card>
                <CardContent>
                    <form onSubmit={handleSubmit(onSubmit)}>
                        <Grid container spacing={3}>
                            <Grid item xs={12}>
                                <Controller
                                    name="member_id"
                                    control={control}
                                    render={({ field }) => (
                                        <Autocomplete
                                            options={membersResponse?.members || []}
                                            getOptionLabel={(option) => `${option.first_name} ${option.last_name} (${option.email})`}
                                            onChange={(_, value) => field.onChange(value?.id)}
                                            renderInput={(params) => (
                                                <TextField
                                                    {...params}
                                                    label={t.memberships.member}
                                                    error={!!errors.member_id}
                                                    helperText={errors.member_id?.message}
                                                />
                                            )}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="plan_id"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            select
                                            label={t.memberships.plan}
                                            error={!!errors.plan_id}
                                            helperText={errors.plan_id?.message}
                                        >
                                            <MenuItem value=""><em>Custom</em></MenuItem>
                                            {plans.map((p) => (
                                                <MenuItem key={p.id} value={p.id}>
                                                    {p.name} - ${p.price}
                                                </MenuItem>
                                            ))}
                                        </TextField>
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="type"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.memberships.type}
                                            error={!!errors.type}
                                            helperText={errors.type?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="start_date"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.memberships.startDate}
                                            type="date"
                                            InputLabelProps={{ shrink: true }}
                                            error={!!errors.start_date}
                                            helperText={errors.start_date?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="end_date"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.memberships.endDate}
                                            type="date"
                                            InputLabelProps={{ shrink: true }}
                                            error={!!errors.end_date}
                                            helperText={errors.end_date?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12} sm={6}>
                                <Controller
                                    name="price"
                                    control={control}
                                    render={({ field }) => (
                                        <TextField
                                            {...field}
                                            fullWidth
                                            label={t.memberships.price}
                                            type="number"
                                            InputProps={{ startAdornment: <InputAdornment position="start">$</InputAdornment> }}
                                            onChange={(e) => field.onChange(parseFloat(e.target.value))}
                                            error={!!errors.price}
                                            helperText={errors.price?.message}
                                        />
                                    )}
                                />
                            </Grid>

                            <Grid item xs={12}>
                                <Box display="flex" gap={2}>
                                    <Button
                                        type="submit"
                                        variant="contained"
                                        size="large"
                                        disabled={createMutation.isPending}
                                    >
                                        {t.members.assignMembershipBtn}
                                    </Button>
                                    <Button
                                        variant="outlined"
                                        size="large"
                                        onClick={() => navigate('/memberships')}
                                    >
                                        {t.common.cancel}
                                    </Button>
                                </Box>
                            </Grid>
                        </Grid>
                    </form>
                </CardContent>
            </Card>
        </Box>
    );
};
